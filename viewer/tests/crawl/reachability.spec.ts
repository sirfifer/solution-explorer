/**
 * Reachability: can a reader actually GET to everything the data holds?
 *
 * This is the defect class the repo has hit repeatedly and that no data-only
 * check can see. The projection is whole, the linter is green, and then the
 * viewer turns out to expose only part of the tree, or to expose it only by a
 * route nobody would find. Two independent channels are walked and compared:
 *
 *   by URL     every component id is addressable as ?component=<id>. This is
 *              the machine route, the one deep links and the front door
 *              promise, and it is exhaustive because it costs one navigation
 *              per component.
 *   by click   the tree is expanded, adaptively, until nothing is left to
 *              expand, and every node that appears is collected. This is the
 *              human route.
 *
 * The two sets must be equal. A component reachable by URL but not by clicking
 * is data with no way in; a node in the DOM that the manifest does not name is
 * the UI inventing structure. Both are reported by name.
 */

import {
  test,
  reportFinding,
  expect,
  gotoState,
  expectNoErrorBoundary,
  expandWholeTree,
  cssEscape,
} from "./fixtures";
import { componentBudget, sampleComponents } from "./contract";

test.describe("reachability", () => {
  test("the app boots and renders the tree the projection describes", async ({
    crawlPage,
    contract,
    recorder,
  }) => {
    await gotoState(crawlPage, {});
    await expectNoErrorBoundary(crawlPage);
    expect(recorder.problems(), "boot must be clean").toEqual([]);

    const nodes = crawlPage.locator('[data-testid="tree-node"]');
    expect(await nodes.count(), "the tree renders at least one node").toBeGreaterThan(0);
    expect(contract.components.size, "the projection holds components").toBeGreaterThan(0);
  });

  test("every component is addressable by URL", async ({ crawlPage, contract, recorder }) => {
    const budget = componentBudget();
    const { chosen, dropped } = sampleComponents(contract, budget);
    test.info().annotations.push({
      type: "coverage",
      description:
        `${chosen.length}/${contract.components.size} components swept` +
        (dropped ? `; ${dropped} dropped by the CRAWL_MAX_COMPONENTS budget` : "; full sweep"),
    });

    const unreachable: string[] = [];
    const wrongComponent: string[] = [];
    const noisy: string[] = [];

    for (const comp of chosen) {
      recorder.reset();
      await gotoState(crawlPage, { component: comp.id });
      const panel = crawlPage.locator('[data-testid="detail-panel"]');
      if ((await panel.count()) === 0) {
        unreachable.push(comp.id);
        continue;
      }
      const shown = await panel.first().getAttribute("data-component-id");
      if (shown !== comp.id) {
        wrongComponent.push(`${comp.id} -> rendered ${shown}`);
      }
      const title = (
        await crawlPage.locator('[data-testid="detail-title"]').first().innerText()
      ).trim();
      if (title !== comp.name) {
        wrongComponent.push(`${comp.id} title is "${title}", expected "${comp.name}"`);
      }
      const problems = recorder.problems();
      if (problems.length) noisy.push(`${comp.id}: ${problems.slice(0, 2).join(" | ")}`);
    }

    reportFinding("reach.unreachable", unreachable, { title: "components whose deep link renders no detail panel" });

    expect(unreachable, "components whose deep link renders no detail panel").toEqual([]);
    reportFinding("reach.wrong_component", wrongComponent, { title: "deep links that land on the wrong component" });
    expect(wrongComponent, "deep links that land on the wrong component").toEqual([]);
    reportFinding("reach.noisy", noisy, { title: "components whose detail view logged an error or a failed request", severity: "warn" });
    expect(noisy, "components whose detail view logged an error or a 404").toEqual([]);
  });

  test("the tree exposes every component the projection holds", async ({
    crawlPage,
    contract,
    recorder,
  }) => {
    await gotoState(crawlPage, {});
    const walk = await expandWholeTree(crawlPage);

    expect(walk.converged, "tree expansion converged rather than hitting the pass cap").toBe(true);
    await expectNoErrorBoundary(crawlPage);
    expect(recorder.problems(), "expanding the whole tree must be clean").toEqual([]);

    const expected = new Set(contract.components.keys());
    const missing = [...expected].filter((id) => !walk.seen.has(id)).sort();
    const invented = [...walk.seen].filter((id) => !expected.has(id)).sort();

    test.info().annotations.push({
      type: "coverage",
      description: `tree exposed ${walk.seen.size} of ${expected.size} components in ${walk.passes} expansion pass(es)`,
    });

    reportFinding("reach.invented_node", invented, { title: "tree nodes the projection does not name" });

    expect(
      invented,
      "tree nodes the projection does not name (the UI inventing structure)",
    ).toEqual([]);
    expect(
      missing.slice(0, 25),
      `${missing.length} component(s) exist in the data but cannot be reached by ` +
        `expanding the tree (showing the first 25)`,
    ).toEqual([]);
  });

  test("every expanded parent reveals exactly the children the data names", async ({
    crawlPage,
    contract,
  }) => {
    // Depth is only trustworthy level by level. Rather than assert a global
    // depth number (which the "Internal Components" grouping legitimately
    // flattens), the whole tree is opened once and then each parent's revealed
    // children are compared to the manifest's child list for that exact id.
    //
    // Parents that the tree never renders as a node are the previous test's
    // business, not this one's; counting them here would report the same defect
    // twice under two names.
    await gotoState(crawlPage, {});
    await expandWholeTree(crawlPage);

    const parents = [...contract.components.values()].filter((c) => c.childIds.length > 0);
    const wrong: string[] = [];
    let checked = 0;

    for (const parent of parents) {
      const node = crawlPage.locator(
        `[data-testid="tree-node"][data-component-id="${cssEscape(parent.id)}"]`,
      );
      if ((await node.count()) === 0) continue;
      checked++;

      if ((await node.first().getAttribute("data-has-children")) !== "true") {
        wrong.push(
          `${parent.id}: has ${parent.childIds.length} children in the data but renders as a leaf`,
        );
        continue;
      }
      const group = crawlPage.locator(
        `[data-testid="tree-children"][data-parent-id="${cssEscape(parent.id)}"]`,
      );
      if ((await group.count()) === 0) {
        wrong.push(`${parent.id}: expanded but reveals no child group`);
        continue;
      }
      const revealed = await group
        .first()
        .locator(':scope > div > [data-testid="tree-node"]')
        .evaluateAll((els) => els.map((el) => el.getAttribute("data-component-id") ?? ""));
      const missing = parent.childIds.filter((id) => !revealed.includes(id));
      const extra = revealed.filter((id) => id && !parent.childIds.includes(id));
      if (missing.length) {
        wrong.push(`${parent.id}: missing ${missing.length} child(ren), first ${missing[0]}`);
      }
      if (extra.length) {
        wrong.push(`${parent.id}: reveals ${extra.length} child(ren) the data does not name`);
      }
    }

    test.info().annotations.push({
      type: "coverage",
      description: `${checked}/${parents.length} parents checked level by level`,
    });
    reportFinding("reach.parent_children", wrong, { title: "parents whose expansion does not match the data" });
    expect(wrong.slice(0, 25), "parents whose expansion does not match the data").toEqual([]);
  });

  test("a deep link reveals its component in the tree, not just in the panel", async ({
    crawlPage,
    contract,
  }) => {
    // Arriving at a component has to leave the reader somewhere they can carry
    // on from. A detail panel with no corresponding row in the navigator is a
    // dead end: there is no "where am I", no siblings, and no way down without
    // starting the walk over from the top. This is the same complaint from the
    // opposite direction as an unreachable component, and it is what "deep
    // links work" has to mean beyond rendering the right title.
    const budget = componentBudget() || 20;
    const nested = [...contract.components.values()]
      .filter((c) => c.depth > 0)
      .sort((a, b) => b.depth - a.depth || a.id.localeCompare(b.id));
    const stride = Math.max(1, Math.floor(nested.length / Math.min(budget, 20)));
    const chosen = nested.filter((_, i) => i % stride === 0).slice(0, Math.min(budget, 20));

    const hidden: string[] = [];
    for (const comp of chosen) {
      await gotoState(crawlPage, { component: comp.id });
      const node = crawlPage.locator(
        `[data-testid="tree-node"][data-component-id="${cssEscape(comp.id)}"]`,
      );
      if ((await node.count()) === 0) {
        hidden.push(`${comp.id} (depth ${comp.depth})`);
      }
    }
    test.info().annotations.push({
      type: "coverage",
      description: `${chosen.length} nested components deep-linked and looked for in the tree`,
    });
    reportFinding("reach.deep_link_hidden", hidden, { title: "deep-linked components whose tree row is never revealed" });
    expect(
      hidden.slice(0, 25),
      "deep-linked components whose tree row is never revealed, leaving the reader " +
        "with a detail panel and no place in the navigator",
    ).toEqual([]);
  });
});
