/**
 * Depth: at every level a reader can reach, is everything that belongs there
 * actually there?
 *
 * Reachability proves you can arrive. This proves that when you arrive, the
 * view is populated in the way the data says it should be. It is written
 * against what the projection knows per component (how many files, how many
 * symbols, which lens arrays name it) rather than against fixed expectations,
 * so it holds for any subject without editing.
 *
 * The rule it enforces everywhere is the honest-empty rule: a tab backed by no
 * data must say so. Blank is a failure, a spinner that never resolves is a
 * failure, and "0 symbols" is a pass. That distinction is the whole point,
 * because a deterministic run with no enrichment legitimately empties several
 * surfaces, and the suite has to tell "correctly empty" from "broken".
 */

import { test,
  reportFinding, expect, gotoState, navigateState, expectNoErrorBoundary } from "./fixtures";
import {
  componentBudget,
  sampleComponents,
  representativeComponent,
  heaviestComponent,
} from "./contract";

/** A panel with no text at all is blank; the honest-empty rule needs words. */
const MIN_PANEL_TEXT = 3;

test.describe("depth", () => {
  test("every tab of every component renders something honest", async ({
    crawlPage,
    contract,
    recorder,
  }) => {
    const budget = componentBudget();
    const { chosen, dropped } = sampleComponents(contract, budget);
    test.info().annotations.push({
      type: "coverage",
      description:
        `${chosen.length}/${contract.components.size} components taken through every tab they offer` +
        (dropped ? `; ${dropped} dropped by the CRAWL_MAX_COMPONENTS budget` : "; full sweep"),
    });

    const blank: string[] = [];
    const broken: string[] = [];
    const noTabs: string[] = [];
    let tabsExercised = 0;

    for (const comp of chosen) {
      recorder.reset();
      await navigateState(crawlPage, { component: comp.id });

      const tabs = crawlPage.locator('[data-testid="detail-tab"]');
      const keys = await tabs.evaluateAll((els) =>
        els.map((el) => el.getAttribute("data-tab") ?? ""),
      );
      if (keys.length === 0) {
        noTabs.push(comp.id);
        continue;
      }

      for (const key of keys) {
        if (!key) continue;
        await crawlPage.locator(`[data-testid="detail-tab"][data-tab="${key}"]`).click();
        const panel = crawlPage.locator('[data-testid="detail-tabpanel"]');
        await expect(panel).toHaveAttribute("data-tab", key);
        tabsExercised++;

        const text = (await panel.innerText()).trim();
        if (text.length < MIN_PANEL_TEXT) {
          blank.push(`${comp.id}#${key}`);
        }
        const problems = recorder.problems();
        if (problems.length) {
          broken.push(`${comp.id}#${key}: ${problems[0]}`);
          recorder.reset();
        }
      }
      await expectNoErrorBoundary(crawlPage);
    }

    test.info().annotations.push({
      type: "coverage",
      description: `${tabsExercised} tab views exercised`,
    });
    reportFinding("depth.no_tabs", noTabs, { title: "components that offer no tabs at all" });
    expect(noTabs.slice(0, 25), "components that offer no tabs at all").toEqual([]);
    reportFinding("depth.blank_tab", blank, { title: "tabs that render nothing, not even an empty state" });
    expect(blank.slice(0, 25), "tabs that render nothing, not even an empty state").toEqual([]);
    reportFinding("depth.tab_error", broken, { title: "tabs that logged an error or a failed request" });
    expect(broken.slice(0, 25), "tabs that logged an error or a failed request").toEqual([]);
  });

  test("a component with symbols shows them, and one without says so", async ({
    crawlPage,
    contract,
  }) => {
    // The strongest per-level claim available without re-deriving the analysis:
    // the detail index states a symbol count per component, and the symbols tab
    // is the surface that count is about. A component the data says is full
    // rendering an empty tab is the "data is there, UI never shows it" bug; a
    // component the data says is empty rendering a spinner is the other half.
    const withSymbols = [...contract.components.values()].filter((c) => c.symbolCount > 0);
    const withoutSymbols = [...contract.components.values()].filter(
      (c) => c.symbolCount === 0 && c.fileCount > 0,
    );
    const budget = componentBudget() || 40;
    const pick = <T,>(arr: T[], n: number): T[] => {
      if (arr.length <= n) return arr;
      const stride = Math.floor(arr.length / n);
      return Array.from({ length: n }, (_, i) => arr[i * stride]);
    };

    const emptyWhenFull: string[] = [];
    for (const comp of pick(withSymbols, Math.min(budget, 40))) {
      await navigateState(crawlPage, { component: comp.id, tab: "symbols" });
      const panel = crawlPage.locator('[data-testid="detail-tabpanel"][data-tab="symbols"]');
      if ((await panel.count()) === 0) {
        emptyWhenFull.push(`${comp.id}: no symbols tab despite ${comp.symbolCount} symbols`);
        continue;
      }
      const text = (await panel.innerText()).trim();
      if (text.length < MIN_PANEL_TEXT) {
        emptyWhenFull.push(`${comp.id}: symbols tab is blank despite ${comp.symbolCount} symbols`);
      }
    }
    reportFinding("depth.symbols_missing", emptyWhenFull, { title: "components whose symbols the data holds but the UI does not show" });
    expect(
      emptyWhenFull.slice(0, 25),
      "components whose symbols the data holds but the UI does not show",
    ).toEqual([]);

    const dishonestlyEmpty: string[] = [];
    for (const comp of pick(withoutSymbols, Math.min(budget, 20))) {
      await navigateState(crawlPage, { component: comp.id, tab: "symbols" });
      const panel = crawlPage.locator('[data-testid="detail-tabpanel"][data-tab="symbols"]');
      if ((await panel.count()) === 0) continue; // the tab may legitimately not exist
      const text = (await panel.innerText()).trim();
      if (text.length < MIN_PANEL_TEXT) {
        dishonestlyEmpty.push(`${comp.id}: symbols tab is blank rather than saying it is empty`);
      }
    }
    reportFinding("depth.dishonest_empty", dishonestlyEmpty, { title: "empty surfaces that render blank instead of an honest empty state" });
    expect(
      dishonestlyEmpty.slice(0, 25),
      "empty surfaces that render blank instead of an honest empty state",
    ).toEqual([]);
  });

  test("every lens the dataset offers can be entered and used", async ({
    crawlPage,
    contract,
    recorder,
  }) => {
    // A per-lens budget is only half the protection. The suite-wide timeout is
    // measured in hours so the full sweeps can finish, which means a step that
    // escapes its own budget could still burn the whole afternoon. This test
    // declares a ceiling proportional to what it is actually allowed to do.
    test.setTimeout(15 * 60 * 1000);

    // The lens list is discovered, never enumerated here: a lens registered
    // next month is exercised by this test the day it ships.
    await gotoState(crawlPage, {});
    const select = crawlPage.locator('[data-testid="lens-select"]');
    if ((await select.count()) === 0) {
      test.info().annotations.push({
        type: "coverage",
        description: "no lens switcher in this build; lens sweep skipped",
      });
      return;
    }
    const lenses = await select
      .locator("option")
      .evaluateAll((els) => els.map((el) => (el as HTMLOptionElement).value));
    expect(lenses.length, "the lens switcher offers at least one lens").toBeGreaterThan(0);

    // A representative component, deliberately NOT the biggest one. Picking
    // the biggest made every lens fail for the same unrelated reason, so the
    // sweep proved nothing about lenses. See representativeComponent.
    const anyComponent = representativeComponent(contract);
    test.info().annotations.push({
      type: "coverage",
      description: `lens representative: ${anyComponent?.id ?? "none"} `
        + `(${anyComponent?.fileCount ?? 0} files, ${anyComponent?.symbolCount ?? 0} symbols)`,
    });

    // Every lens is entered under its own hard budget.
    //
    // Learned the expensive way: on the VS Code projection one lens spun the
    // renderer at 100% CPU and 900 MB for over half an hour, and because the
    // step had no bound the SUITE hung with it, reporting nothing. A harness
    // that hangs instead of reporting is the same failure as a product that
    // hangs instead of rendering, so a lens that will not settle is now a
    // recorded finding that names the lens and moves on to the next one.
    const LENS_BUDGET_MS = 45_000;
    const broken: string[] = [];
    const timings: string[] = [];

    // Every wait below must be one Playwright ENFORCES FROM NODE.
    //
    // The first version of this used page.evaluate to ask whether the page had
    // settled. page.evaluate takes an argument, not options, so it carries no
    // timeout at all, and on a main thread spinning at 100% CPU it simply never
    // returns. The budget existed and never fired, and the suite hung exactly
    // as the product had. waitForFunction and expect both time out Node-side,
    // so they still fail when the page is too busy to answer.
    for (const lens of lenses) {
      recorder.reset();
      const started = Date.now();
      let failure: string | null = null;
      try {
        await gotoState(crawlPage, { component: anyComponent?.id, lens });
        await crawlPage
          .locator('[data-testid="lens-select"]')
          .selectOption(lens, { timeout: LENS_BUDGET_MS });
        // Settling means the page can answer a question, not that a fixed sleep
        // elapsed. A page too busy to run this predicate is the finding.
        await crawlPage.waitForFunction(() => document.readyState === "complete", undefined, {
          timeout: LENS_BUDGET_MS,
        });
        await expectNoErrorBoundary(crawlPage);
      } catch (err) {
        failure = (err as Error).message.split("\n")[0];
      }

      const elapsed = Math.round((Date.now() - started) / 1000);
      if (failure) {
        broken.push(`lens ${lens}: not usable within ${elapsed}s (${failure})`);
        // The page is probably still spinning, and a spinning page fails every
        // lens after it. Park it somewhere inert so the rest get a fair test.
        await crawlPage.goto("about:blank", { timeout: 10_000 }).catch(() => {});
        continue;
      }
      timings.push(`${lens} ${elapsed}s`);
      const problems = recorder.problems();
      if (problems.length) broken.push(`lens ${lens}: ${problems[0]}`);
    }

    test.info().annotations.push({
      type: "coverage",
      description: `${lenses.length} lens(es) exercised: ${lenses.join(", ")}`,
    });
    test.info().annotations.push({
      type: "coverage",
      description: `lens entry times: ${timings.join(", ") || "none completed"}`,
    });
    expect(broken, "lenses that error or will not settle when entered").toEqual([]);
  });

  test("the heaviest component in the subject can still be opened", async ({
    crawlPage,
    contract,
  }) => {
    // The worst case, tested deliberately and once.
    //
    // The biggest component is usually the most interesting thing in the whole
    // subject and therefore among the likeliest clicks. On VS Code it is
    // src/vs/workbench, 3,625 files and 47,339 symbols in a 50 MB shard, and
    // opening it pins the browser at 100% CPU indefinitely. A demo where the
    // most obvious thing to click kills the tab is worse than one missing it.
    //
    // Bounded so this test reports rather than hangs, which is the mistake the
    // lens sweep originally made. The budget is generous because a big
    // component is legitimately slow; what is not legitimate is never
    // finishing.
    test.setTimeout(4 * 60 * 1000);
    const OPEN_BUDGET_MS = 60_000;

    const heaviest = heaviestComponent(contract);
    if (!heaviest) return;
    test.info().annotations.push({
      type: "coverage",
      description:
        `heaviest component: ${heaviest.id} ` +
        `(${heaviest.fileCount} files, ${heaviest.symbolCount} symbols)`,
    });

    const started = Date.now();
    let failure: string | null = null;
    try {
      await gotoState(crawlPage, { component: heaviest.id });
      // waitForFunction and expect time out from Node, so they still fail when
      // the page is too busy to answer. page.evaluate would not.
      await crawlPage.waitForFunction(() => document.readyState === "complete", undefined, {
        timeout: OPEN_BUDGET_MS,
      });
      await expect(
        crawlPage.locator(`[data-testid="detail-panel"]`),
      ).toHaveAttribute("data-component-id", heaviest.id, { timeout: OPEN_BUDGET_MS });
      await expectNoErrorBoundary(crawlPage);
    } catch (err) {
      failure = (err as Error).message.split("\n")[0];
    }
    const elapsed = Math.round((Date.now() - started) / 1000);
    test.info().annotations.push({
      type: "coverage",
      description: `heaviest component opened in ${elapsed}s`,
    });

    expect(
      failure,
      `the subject's heaviest component (${heaviest.id}: ${heaviest.fileCount} files, ` +
        `${heaviest.symbolCount} symbols) did not open within ${OPEN_BUDGET_MS / 1000}s. ` +
        `This is a derivation problem before it is a rendering one: no viewer copes ` +
        `with a component this large, so the fix belongs upstream in how components ` +
        `are grouped. scripts/lint-projection.py's census.component_weight rule ` +
        `catches the same thing without needing a browser.`,
    ).toBeNull();
  });

  test("enrichment-only surfaces are consistent with the dataset's posture", async ({
    crawlPage,
    contract,
  }) => {
    // A deterministic run carries no ai_enhance, so the AI tab must either be
    // absent or say plainly that there is nothing. Half a posture is the defect:
    // some components offering enriched content and others not, in a dataset
    // that is uniformly one or the other.
    const share = contract.enrichedShare;
    test.info().annotations.push({
      type: "coverage",
      description: `dataset enrichment share ${(share * 100).toFixed(1)}%`,
    });
    expect(
      share === 0 || share === 1,
      `enrichment is partial (${(share * 100).toFixed(1)}% of components); the UI cannot ` +
        `report a coherent posture for a dataset that is neither enriched nor plain`,
    ).toBe(true);

    const budget = componentBudget() || 25;
    const { chosen } = sampleComponents(contract, Math.min(budget, 25));
    const inconsistent: string[] = [];
    for (const comp of chosen) {
      await navigateState(crawlPage, { component: comp.id });
      const aiTab = crawlPage.locator('[data-testid="detail-tab"][data-tab="ai"]');
      const present = (await aiTab.count()) > 0;
      if (!present) continue;
      await aiTab.click();
      const text = (
        await crawlPage.locator('[data-testid="detail-tabpanel"][data-tab="ai"]').innerText()
      ).trim();
      if (text.length < MIN_PANEL_TEXT) {
        inconsistent.push(`${comp.id}: AI tab present but blank`);
      }
    }
    reportFinding("depth.ai_surface", inconsistent, { title: "AI surfaces that neither carry content nor say why" });
    expect(inconsistent.slice(0, 25), "AI surfaces that neither carry content nor say why").toEqual(
      [],
    );
  });
});
