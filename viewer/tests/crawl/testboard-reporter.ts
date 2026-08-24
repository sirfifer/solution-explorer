/**
 * Playwright reporter that publishes a crawl run to the testboard.
 *
 * The point is that a run is observable by whoever wants to watch it, not only
 * by whoever started it. Somebody launching the suite from a terminal, an agent
 * launching it from a session, and CI launching it from a workflow all write
 * the same two files into the same place, so the dashboard shows the run either
 * way and nobody has to be standing over the process to know what it is doing.
 *
 * Two files per run, both written as the run happens rather than at the end:
 *
 *   run.json      the record: what is being crawled, against what versions,
 *                 how far along, what the verdict was. Rewritten on every
 *                 event so a reader always sees current truth.
 *   events.jsonl  append-only log, one JSON object per line. Append-only
 *                 because a dashboard tailing a file must never see a
 *                 half-rewritten history, and because a crashed run leaves its
 *                 events behind rather than losing them.
 *
 * A run that dies without an end event stays `running` in its own record. The
 * dashboard decides when that has gone stale (see scripts/testboard.py); the
 * reporter never lies about having finished.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import type {
  FullConfig,
  FullResult,
  Reporter,
  Suite,
  TestCase,
  TestResult,
} from "@playwright/test/reporter";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, "..", "..", "..");

function readJson(file: string): any {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

/** Everything the dashboard needs to answer "which build produced this run". */
function versionStamp(dataDir: string | undefined) {
  const pkg = readJson(path.join(REPO_ROOT, "viewer", "package.json"));
  let analyzerVersion: string | null = null;
  try {
    const init = fs.readFileSync(path.join(REPO_ROOT, "analyzer", "__init__.py"), "utf8");
    analyzerVersion = init.match(/__version__\s*=\s*"([^"]+)"/)?.[1] ?? null;
  } catch {
    /* running outside a checkout */
  }
  const manifest = dataDir ? readJson(path.join(dataDir, "manifest.json")) : null;
  return {
    viewer_version: pkg?.version ?? null,
    analyzer_version: analyzerVersion,
    dataset: manifest
      ? {
          name: manifest.name ?? null,
          generated_at: manifest.generated_at ?? null,
          analyzer_version: manifest.analyzer_version ?? null,
          subject_sha: manifest.activity?.provenance?.head ?? null,
          components: manifest.component_detail_index
            ? Object.keys(manifest.component_detail_index).length
            : null,
          enriched: manifest.components
            ? undefined // filled by the suite's own census; cheap here would mean walking the tree
            : null,
        }
      : null,
  };
}

/**
 * How often the record is re-stamped while a single case is still running.
 *
 * Load bearing, and learned from a false alarm. The board decides a run is
 * dead by how long its record has gone untouched, and the record was only
 * written between cases. A legitimately long case, the lens sweep takes many
 * minutes, therefore looked exactly like a crashed process and the board
 * called a healthy run stalled. A board that cries wolf is worse than no
 * board, so a live run says "still here" on a timer, independently of whether
 * it has anything new to report.
 */
const HEARTBEAT_MS = 20_000;

export default class TestboardReporter implements Reporter {
  private runDir!: string;
  private eventsPath!: string;
  private record: any;
  private startedAt = 0;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private currentStarted: number | null = null;

  onBegin(config: FullConfig, suite: Suite): void {
    this.startedAt = Date.now();
    const stamp = new Date(this.startedAt).toISOString().replace(/[:.]/g, "-");
    const dataDir =
      process.env.CRAWL_DATA_DIR ??
      (process.env.CRAWL_SERVE_DIR
        ? path.join(process.env.CRAWL_SERVE_DIR, "architecture")
        : undefined);
    const resolvedDataDir = dataDir ? path.resolve(dataDir) : undefined;
    const versions = versionStamp(resolvedDataDir);
    const subject = versions.dataset?.name ?? "unknown";

    const root =
      process.env.TESTBOARD_DIR ?? path.join(REPO_ROOT, ".testboard", "runs");
    this.runDir = path.join(root, `${stamp}-crawl-${subject}`);
    fs.mkdirSync(this.runDir, { recursive: true });
    this.eventsPath = path.join(this.runDir, "events.jsonl");

    this.record = {
      testboard_version: 1,
      id: path.basename(this.runDir),
      kind: "crawl",
      subject,
      status: "running",
      started_at: new Date(this.startedAt).toISOString(),
      ended_at: null,
      duration_ms: null,
      data_dir: resolvedDataDir ?? null,
      base_url: process.env.CRAWL_BASE_URL ?? null,
      budget: process.env.CRAWL_MAX_COMPONENTS ?? "0 (full sweep)",
      versions,
      total: suite.allTests().length,
      completed: 0,
      passed: 0,
      failed: 0,
      skipped: 0,
      current: null,
      cases: [],
      coverage: [],
      findings: [],
      finding_totals: {
        instances: 0, distinct: 0,
        errors: 0, error_instances: 0,
        warnings: 0, warning_instances: 0,
      },
    };
    this.emit({ type: "run_start", total: this.record.total, subject });
    this.flush();

    // The heartbeat writes the record, not an event, so a long case does not
    // bloat events.jsonl with hundreds of "still alive" lines. The board reads
    // liveness from the record's mtime, which is exactly what this refreshes.
    this.heartbeat = setInterval(() => {
      this.record.heartbeat_at = new Date().toISOString();
      this.record.current_elapsed_ms = this.currentStarted
        ? Date.now() - this.currentStarted
        : null;
      this.flush();
    }, HEARTBEAT_MS);
    // Never hold the process open on the board's account.
    this.heartbeat.unref?.();
  }

  onTestBegin(test: TestCase): void {
    this.currentStarted = Date.now();
    this.record.current = test.titlePath().slice(-2).join(" › ");
    this.emit({ type: "case_start", title: this.record.current });
    this.flush();
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    const title = test.titlePath().slice(-2).join(" › ");
    this.record.completed += 1;
    if (result.status === "passed") this.record.passed += 1;
    else if (result.status === "skipped") this.record.skipped += 1;
    else this.record.failed += 1;

    // The suite reports its own reach through annotations ("94/94 components
    // swept"); surfacing them is what turns a green tick into a claim you can
    // check, and what makes a silently budgeted run visible as budgeted.
    const coverage = result.status
      ? test.annotations.filter((a) => a.type === "coverage").map((a) => a.description ?? "")
      : [];
    for (const line of coverage) {
      if (line) this.record.coverage.push(line);
    }

    // The first line of a failure is the suite's own message, which is written
    // to be the finding rather than a stack frame.
    const message = (result.error?.message ?? "")
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)[0];

    // Findings the case recorded before asserting. A pass/fail tally cannot say
    // whether one problem was seen fifty times or fifty separate problems were
    // found, and those call for completely different responses, so the case
    // carries its findings and the run carries their totals.
    const findings = test.annotations
      .filter((a) => a.type === "finding")
      .map((a) => {
        try {
          return JSON.parse(a.description ?? "{}");
        } catch {
          return null;
        }
      })
      .filter(Boolean)
      .map((f: any) => ({
        // Stable across runs so the issue ledger can track one problem over
        // time. Derived from the rule rather than the message, since a crawl
        // finding's rule already names the kind of problem exactly.
        id: `${f.rule}`,
        rule: f.rule,
        severity: f.severity ?? "error",
        title: f.title ?? f.rule,
        instances: f.instances ?? 0,
        examples: f.examples ?? [],
        nature: "unclassified",
        case_title: title,
      }));
    for (const f of findings) this.record.findings.push(f);

    const entry = {
      title,
      status: result.status,
      duration_ms: result.duration,
      coverage,
      findings,
      instances: findings.reduce((n: number, f: any) => n + f.instances, 0),
      distinct: findings.length,
      message: result.status === "passed" ? null : message ?? null,
    };
    this.record.cases.push(entry);
    this.record.current = null;
    this.currentStarted = null;
    this.record.current_elapsed_ms = null;
    this.emit({ type: "case_end", ...entry });
    this.flush();
  }

  onEnd(result: FullResult): void {
    if (this.heartbeat) clearInterval(this.heartbeat);
    const all = this.record.findings as any[];
    this.record.finding_totals = {
      instances: all.reduce((n, f) => n + f.instances, 0),
      distinct: all.length,
      errors: all.filter((f) => f.severity === "error").length,
      error_instances: all
        .filter((f) => f.severity === "error")
        .reduce((n, f) => n + f.instances, 0),
      warnings: all.filter((f) => f.severity === "warn").length,
      warning_instances: all
        .filter((f) => f.severity === "warn")
        .reduce((n, f) => n + f.instances, 0),
    };
    this.record.status = result.status === "passed" ? "passed" : "failed";
    this.record.ended_at = new Date().toISOString();
    this.record.duration_ms = Date.now() - this.startedAt;
    this.record.current = null;
    this.emit({
      type: "run_end",
      status: this.record.status,
      passed: this.record.passed,
      failed: this.record.failed,
    });
    this.flush();
  }

  private emit(event: Record<string, unknown>): void {
    try {
      fs.appendFileSync(
        this.eventsPath,
        JSON.stringify({ ts: new Date().toISOString(), ...event }) + "\n",
        "utf8",
      );
    } catch {
      /* observability must never be able to fail a test run */
    }
  }

  private flush(): void {
    try {
      fs.writeFileSync(
        path.join(this.runDir, "run.json"),
        JSON.stringify(this.record, null, 2) + "\n",
        "utf8",
      );
    } catch {
      /* same: never fail the run over a dashboard write */
    }
  }
}
