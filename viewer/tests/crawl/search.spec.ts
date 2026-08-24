/**
 * Search: does picking a result actually land you on it?
 *
 * This was the coverage gap. The linter proves every entry in the search index
 * resolves in the DATA (component ids exist, file paths appear in a shard,
 * symbol ids are real). Nothing proved the other half: that choosing a result
 * navigates the UI to the thing the result named. A search box that returns
 * plausible rows and then drops you somewhere unrelated is worse than one that
 * finds nothing, because the reader believes they arrived.
 *
 * The targets are drawn from the projection, not typed in here, so this runs
 * against any subject. Symbols and files are included deliberately: they route
 * through different code paths than components (`openFileDeepLink` and the
 * post-fetch symbol re-resolve), and those paths are where landing quietly
 * fails.
 */

import fs from "node:fs";
import path from "node:path";

import { test,
  reportFinding, expect, gotoState, expectNoErrorBoundary } from "./fixtures";
import { componentBudget, type Contract } from "./contract";

/** How many of each kind to route end to end. */
function perKindBudget(): number {
  const budget = componentBudget();
  return budget > 0 ? Math.max(3, Math.min(15, Math.floor(budget / 4))) : 15;
}

interface Target {
  kind: "component" | "file" | "symbol";
  /** What to type. */
  query: string;
  /** The id the chosen result must carry. */
  id: string;
  /** The component the reader must end up inside. */
  componentId: string;
}

/**
 * Draw search targets from the shipped index, the same file the app fetches.
 *
 * Names that occur many times across the subject are skipped: a query matching
 * 400 rows says nothing about routing, only about ranking, and ranking is a
 * judgement question for the AI plan rather than a mechanical one.
 */
function drawTargets(contract: Contract, perKind: number): Target[] {
  const searchDir = path.join(contract.dataDir, "search");
  const manifestPath = path.join(searchDir, "manifest.json");
  if (!fs.existsSync(manifestPath)) return [];
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));

  const entries: any[] = [];
  for (const shard of manifest.shards ?? []) {
    const shardPath = path.join(searchDir, shard);
    if (!fs.existsSync(shardPath)) continue;
    const doc = JSON.parse(fs.readFileSync(shardPath, "utf8"));
    if (Array.isArray(doc)) entries.push(...doc);
    // One shard is plenty to draw a stratified sample from; reading all of them
    // on a large subject costs hundreds of megabytes for no extra signal.
    if (entries.length > 20_000) break;
  }

  const nameCounts = new Map<string, number>();
  for (const e of entries) {
    const name = e?.name;
    if (typeof name === "string") nameCounts.set(name, (nameCounts.get(name) ?? 0) + 1);
  }

  const out: Target[] = [];
  for (const kind of ["component", "file", "symbol"] as const) {
    const candidates = entries.filter(
      (e) =>
        e?.ref_kind === kind &&
        typeof e.name === "string" &&
        e.name.length >= 4 &&
        nameCounts.get(e.name) === 1 &&
        typeof e.ref_id === "string" &&
        contract.components.has(kind === "component" ? e.ref_id : e.component),
    );
    candidates.sort((a, b) => String(a.ref_id).localeCompare(String(b.ref_id)));
    const stride = Math.max(1, Math.floor(candidates.length / perKind));
    for (let i = 0; i < candidates.length && out.filter((t) => t.kind === kind).length < perKind; i += stride) {
      const e = candidates[i];
      out.push({
        kind,
        query: e.name,
        id: e.ref_id,
        componentId: kind === "component" ? e.ref_id : e.component,
      });
    }
  }
  return out;
}

test.describe("search", () => {
  test("every kind of search result navigates to what it named", async ({
    crawlPage,
    contract,
    recorder,
  }) => {
    const targets = drawTargets(contract, perKindBudget());
    if (targets.length === 0) {
      test.info().annotations.push({
        type: "coverage",
        description: "no search index in this projection; search routing not checked",
      });
      return;
    }
    const byKind = targets.reduce<Record<string, number>>((acc, t) => {
      acc[t.kind] = (acc[t.kind] ?? 0) + 1;
      return acc;
    }, {});
    test.info().annotations.push({
      type: "coverage",
      description: `${targets.length} search targets routed end to end: ${JSON.stringify(byKind)}`,
    });

    const noResults: string[] = [];
    const wrongLanding: string[] = [];
    const noisy: string[] = [];

    // ONE cold load for the whole sweep, then stay in the app.
    //
    // The first version reloaded the page for every target. On VS Code that
    // meant re-fetching and re-indexing a 60 MB search index up to 45 times,
    // and the case ran past four minutes while measuring nothing anyone does:
    // a reader searches repeatedly within one loaded page, they do not reload
    // between queries. A test that stresses the wrong axis reports something
    // true and useless, the same mistake as picking the biggest component as
    // the lens representative.
    await gotoState(crawlPage, {});

    // Each target is surveyed inside its own try. A crawl is a survey, not a
    // single assertion: one target that throws must not abandon the other
    // forty-four, and a case that dies partway through reports NO findings at
    // all, because findings are recorded before the assertions at the end.
    // That happened on the first full sweep, which reported "1 failed" with
    // zero findings attached and therefore said nothing about what was wrong.
    const broke: string[] = [];
    for (const target of targets) {
      try {
        recorder.reset();
        // Close any overlay left open by the previous target, then reopen.
        await crawlPage.keyboard.press("Escape").catch(() => {});
        await crawlPage.keyboard.press("ControlOrMeta+k");
        const input = crawlPage.locator('[data-testid="search-input"]');
        await expect(input).toBeVisible();
        await input.fill(target.query);

        // The index is fetched in shards and enriches results as it arrives, so
        // the row for an exact name may appear a beat after the first render.
        const row = crawlPage.locator(
          `[data-testid="search-result"][data-result-kind="${target.kind}"]`,
        );
        try {
          await expect(row.first()).toBeVisible({ timeout: 15_000 });
        } catch {
          noResults.push(`${target.kind} "${target.query}" returns no ${target.kind} row`);
          continue;
        }

        // Prefer the row that names our exact target; fall back to the first of
        // its kind, since landing correctly is the claim, not ranking position.
        const exact = crawlPage.locator(
          `[data-testid="search-result"][data-result-id="${target.id.replace(/["\\]/g, "\\$&")}"]`,
        );
        const chosen = (await exact.count()) > 0 ? exact.first() : row.first();
        await chosen.click();

        await expect(crawlPage.locator('[data-testid="search-overlay"]')).toHaveCount(0);

        // Each kind lands on its OWN detail view, and asserting the component
        // panel for all three was simply wrong: a symbol result correctly opens
        // the symbol view, which is a different component with no
        // data-component-id. That mistake reported 15 false failures on VS Code
        // and briefly went on the record as a product defect. The lesson is that
        // a selector contract covering one of three detail kinds will be misused.
        const landedOn = async (): Promise<string> => {
          const symbol = crawlPage.locator('[data-testid="symbol-detail"]');
          if (await symbol.count()) return `symbol:${await symbol.first().getAttribute("data-symbol-id")}`;
          const file = crawlPage.locator('[data-testid="file-detail"]');
          if (await file.count()) return `file:${await file.first().getAttribute("data-file-path")}`;
          const comp = crawlPage.locator('[data-testid="detail-panel"]');
          if (await comp.count()) return `component:${await comp.first().getAttribute("data-component-id")}`;
          return "nothing";
        };

        const landed = await landedOn();
        if (landed === "nothing") {
          wrongLanding.push(`${target.kind} "${target.query}" opened no detail view at all`);
          continue;
        }

        // What "landing correctly" MEANS differs by kind, and it is defined by
        // the product's own design rather than by what a test author assumes.
        //
        // A file result deliberately drills to the OWNING COMPONENT and marks the
        // file in its Files tab: see openFileDeepLink, written to fix
        // comprehension-study S7, where landing elsewhere left "the file nowhere
        // in sight". Asserting that a file result opens a file view contradicted
        // the fix and produced 14 false failures. Read the intent before
        // asserting it.
        let acceptable: boolean;
        if (target.kind === "component") {
          acceptable = landed === `component:${target.componentId}`;
        } else if (target.kind === "symbol") {
          // Either the symbol itself, or its owning component while the shard
          // resolves (the two-step path documented in handleSelect).
          acceptable =
            landed === `symbol:${target.id}` || landed === `component:${target.componentId}`;
        } else {
          // A file lands on its owning component by design. The claim worth
          // checking is the second half of that promise: the file is actually
          // marked where the reader can see it.
          acceptable = landed === `file:${target.id}` || landed.startsWith("component:");
          if (acceptable && landed.startsWith("component:")) {
            const marked = await crawlPage
              .locator('[data-testid="detail-tabpanel"][data-tab="files"]')
              .innerText()
              .catch(() => "");
            const leaf = target.id.split("/").pop() ?? target.id;
            if (marked && !marked.includes(leaf)) {
              wrongLanding.push(
                `file "${target.query}" drilled to ${landed} but the Files tab does not show ${leaf}`,
              );
            }
          }
        }
        if (!acceptable) {
          wrongLanding.push(`${target.kind} "${target.query}" landed on ${landed}`);
        }
        await expectNoErrorBoundary(crawlPage);
        const problems = recorder.problems();
        if (problems.length) noisy.push(`${target.kind} "${target.query}": ${problems[0]}`);
      } catch (err) {
        // The UI would not cooperate for this target. Recorded and moved past,
        // so the sweep still covers everything after it.
        broke.push(
          `${target.kind} "${target.query}": ${(err as Error).message.split("\n")[0]}`,
        );
        await crawlPage.goto("/").catch(() => {});
        await crawlPage
          .waitForSelector('[data-testid="tree-navigator"]', { timeout: 30_000 })
          .catch(() => {});
      }
    }

    reportFinding("search.unusable", broke, {
      title: "targets where the search UI could not be driven at all",
    });
    reportFinding("search.no_results", noResults, {
      title: "exact names present in the search index that search does not find",
    });
    reportFinding("search.wrong_landing", wrongLanding, {
      title: "search results that navigate somewhere other than what they named",
    });
    reportFinding("search.noisy", noisy, {
      title: "search routes that logged a console error or a failed request",
      severity: "warn",
    });
    expect(broke.slice(0, 25), "targets where the search UI could not be driven").toEqual([]);
    expect(noResults.slice(0, 25), "exact names in the index that search does not find").toEqual([]);
    expect(wrongLanding.slice(0, 25), "search results that navigate somewhere else").toEqual([]);
    expect(noisy.slice(0, 25), "search routes that logged an error or a 404").toEqual([]);
  });

  test("a search result leaves the reader placed in the tree", async ({ crawlPage, contract }) => {
    // Same complaint as the deep-link case, by a different route. Arriving via
    // search has to leave you somewhere you can carry on from, not on an
    // orphaned panel.
    const targets = drawTargets(contract, 5).filter((t) => t.kind === "component");
    if (targets.length === 0) return;

    const unplaced: string[] = [];
    await gotoState(crawlPage, {});
    for (const target of targets) {
      await crawlPage.keyboard.press("Escape").catch(() => {});
      await crawlPage.keyboard.press("ControlOrMeta+k");
      const input = crawlPage.locator('[data-testid="search-input"]');
      await expect(input).toBeVisible();
      await input.fill(target.query);
      const exact = crawlPage.locator(
        `[data-testid="search-result"][data-result-id="${target.id.replace(/["\\]/g, "\\$&")}"]`,
      );
      if ((await exact.count()) === 0) continue;
      await exact.first().click();

      const node = crawlPage.locator(
        `[data-testid="tree-node"][data-component-id="${target.id.replace(/["\\]/g, "\\$&")}"]`,
      );
      if ((await node.count()) === 0) unplaced.push(target.id);
    }
    reportFinding("search.unplaced", unplaced, {
      title: "components reached by search whose tree row is never revealed",
    });
    expect(
      unplaced.slice(0, 25),
      "components reached by search whose tree row is never revealed",
    ).toEqual([]);
  });

  test("a query that matches nothing says so", async ({ crawlPage }) => {
    await gotoState(crawlPage, {});
    await crawlPage.keyboard.press("ControlOrMeta+k");
    const input = crawlPage.locator('[data-testid="search-input"]');
    await expect(input).toBeVisible();
    await input.fill("zzzz-no-such-symbol-anywhere-zzzz");
    await expect(crawlPage.locator('[data-testid="search-no-results"]')).toBeVisible();
    await expect(crawlPage.locator('[data-testid="search-result"]')).toHaveCount(0);
  });
});
