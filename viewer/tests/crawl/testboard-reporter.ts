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

/**
 * A subject name reduced to something safe to use as one path segment.
 *
 * Everything outside a conservative allowlist becomes "-", runs are collapsed,
 * and the result is capped and never empty. Deliberately an allowlist: the
 * failure mode of guessing which characters are dangerous is that the one you
 * did not think of is the one that shows up.
 */
function pathSafe(value: string): string {
  const cleaned = value
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .replace(/^[.-]+/, "")
    .replace(/-+$/, "")
    .slice(0, 64);
  return cleaned || "unknown";
}

export default class TestboardReporter implements Reporter {
  private runDir!: string;
  private eventsPath!: string;
  private record: any;
  private startedAt = 0;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  /** Set once the first test actually starts, which a listing never does. */
  private published = false;

  /** Create the run directory the first time real work begins. */
  private publish(): void {
    if (this.published) return;
    this.published = true;
    fs.mkdirSync(this.runDir, { recursive: true });
  }
  private currentStarted: number | null = null;
  /** What this build exposes, keyed by fact name. Written as discovery.json. */
  private discovery: Record<string, unknown> = {};

  onBegin(config: FullConfig, suite: Suite): void {
    // A listing is not a run, and nothing in onBegin can tell the difference:
    // `playwright test --list` instantiates reporters AND builds the full suite,
    // so counting tests here says 13 either way. The one signal that separates
    // them is that a listing never starts a test.
    //
    // So the record is prepared here and published on the first test that
    // actually begins. Three listings had already reached the board as runs
    // reporting 0 passed, 0 failed and a status of "passed", under the subject
    // "unknown" because a listing sets no serve directory either. A green row
    // for work that never happened is worse than a missing row: it is the board
    // asserting something it has no evidence for.
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
    // The directory name gets a sanitised subject; the record below keeps the
    // real one. `subject` is read from the analysed project's manifest, so it
    // is the SUBJECT's data rather than ours, and a repo-style name such as
    // "microsoft/large-repository-validation" would silently nest the run two levels down where the
    // board cannot find it. A leading ".." would climb out of .testboard
    // entirely, and ":" is simply not a legal filename character on Windows.
    const targetTag = process.env.CRAWL_REMOTE === "1" ? "-remote" : "";
    this.runDir = path.join(root, `${stamp}-crawl-${pathSafe(subject)}${targetTag}`);
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
      // A run against the deployed site and a run against a locally assembled
      // root are different claims, and telling them apart on the board must not
      // depend on reading a URL and guessing. globalSetup sets these when it
      // mirrors a remote projection; a local run leaves them false and null.
      remote: process.env.CRAWL_REMOTE === "1",
      remote_generated_at: process.env.CRAWL_REMOTE_GENERATED_AT || null,
      profile: process.env.CRAWL_PROFILE ?? "quick",
      budget: process.env.CRAWL_MAX_COMPONENTS ?? "0 (full sweep)",
      versions,
      total: suite.allTests().length,
      completed: 0,
      passed: 0,
      failed: 0,
      skipped: 0,
      current: null,
      cases: [],
      // Set when the contract-presence gate fires: the build under test does
      // not publish the selector contract, so most of the suite was skipped.
      limited: false,
      // Free-text notes from the parameters file, so a run record says what the
      // person who set the parameters meant by them.
      params_notes: null as string | null,
      params_source: process.env.CRAWL_PARAMS ?? null,
      // Per-project tallies. The mobile project is a real project with real
      // failures, and rolling it into one number would hide exactly the case
      // the second viewport exists to catch.
      by_project: {} as Record<string, { passed: number; failed: number; skipped: number }>,
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

  /** The project a case belongs to, so desktop and mobile stay distinguishable. */
  private projectOf(test: TestCase): string {
    return test.parent?.project()?.name ?? "default";
  }

  onTestBegin(test: TestCase): void {
    this.publish();
    this.currentStarted = Date.now();
    this.record.current = `[${this.projectOf(test)}] ` + test.titlePath().slice(-2).join(" › ");
    this.emit({ type: "case_start", title: this.record.current });
    this.flush();
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    if (!this.published) return;
    const project = this.projectOf(test);
    const title = `[${project}] ` + test.titlePath().slice(-2).join(" › ");
    this.record.completed += 1;
    const tally = (this.record.by_project[project] ??= { passed: 0, failed: 0, skipped: 0 });
    if (result.status === "passed") {
      this.record.passed += 1;
      tally.passed += 1;
    } else if (result.status === "skipped") {
      this.record.skipped += 1;
      tally.skipped += 1;
    } else {
      this.record.failed += 1;
      tally.failed += 1;
    }

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

    // Discoveries: what this build exposes, as opposed to what is wrong with
    // it. Collected here and written once at the end as discovery.json.
    for (const a of test.annotations) {
      if (a.type !== "discovery") continue;
      try {
        const { key, value } = JSON.parse(a.description ?? "{}");
        if (typeof key === "string") this.discovery[key] = value;
      } catch {
        /* a malformed discovery must never fail a run */
      }
    }

    const entry = {
      title,
      project,
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
    // Nothing ever started, so this was a listing and there is nothing to say.
    if (!this.published) return;
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
    // A run whose contract-presence gate fired covered a fraction of what the
    // suite can check, and calling that "passed" on the board would be the
    // board asserting something it has no evidence for. It is reported as
    // LIMITED: not a failure (nothing was wrong with what did run), but never
    // green either.
    const limited = (this.record.coverage as string[]).some((line) =>
      line.startsWith("contract.absent:"),
    );
    // Every case skipped for the same absence is not a run at all. Saying
    // "failed" would blame the product for attributes it does not carry, and
    // saying "passed" would claim evidence that was never gathered.
    if (limited && this.record.passed === 0 && this.record.failed === 0) {
      this.record.status = "limited";
      this.record.limited = true;
      this.record.ended_at = new Date().toISOString();
      this.record.duration_ms = Date.now() - this.startedAt;
    }
    this.record.limited = limited;
    this.record.status =
      result.status !== "passed" ? "failed" : limited ? "limited" : "passed";
    this.record.ended_at = new Date().toISOString();
    this.record.duration_ms = Date.now() - this.startedAt;
    this.record.current = null;
    // The slowest cases, named. The owner's standard is that Playwright is
    // fast and a slow suite means the suite is being used badly, so the record
    // has to make "which cases cost the time" answerable without a stopwatch.
    this.record.slowest = [...(this.record.cases as any[])]
      .sort((a, b) => (b.duration_ms ?? 0) - (a.duration_ms ?? 0))
      .slice(0, 8)
      .map((c) => ({ title: c.title, duration_ms: c.duration_ms, status: c.status }));

    this.emit({
      type: "run_end",
      status: this.record.status,
      passed: this.record.passed,
      failed: this.record.failed,
    });
    this.flush();
    this.writeDiscovery();
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

  /**
   * `discovery.json`: the machine-readable inventory of what this version
   * exposes, so a later orchestrator reads it instead of re-deriving it by
   * running the suite again and parsing prose.
   */
  private writeDiscovery(): void {
    try {
      fs.writeFileSync(
        path.join(this.runDir, "discovery.json"),
        JSON.stringify(
          {
            run_id: this.record.id,
            subject: this.record.subject,
            base_url: this.record.base_url,
            remote: this.record.remote,
            limited: this.record.limited,
            params_source: this.record.params_source,
            generated_at: new Date().toISOString(),
            ...this.discovery,
          },
          null,
          2,
        ) + "\n",
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
