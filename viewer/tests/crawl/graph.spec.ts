/**
 * The graph canvas: does the diagram do what it looks like it does?
 *
 * The crawl deliberately stayed off the canvas for a long time, and the reason
 * is still right: node POSITIONS are layout-engine output, and asserting on
 * them is asserting on elk's arithmetic, which changes for reasons that have
 * nothing to do with whether the product works. Nothing here asserts a
 * position.
 *
 * What is asserted is behaviour that the reader can name and that the app
 * itself promises: which nodes belong at a level, that clicking one selects it,
 * that clicking the empty pane clears the selection, that selecting something
 * off-screen brings it into view, and that double-clicking a node with children
 * drills into it and Home comes back. Every one of those has broken before, and
 * every one is invisible to a test that only reads the tree and the URL.
 *
 * Two of the app's own rules are respected rather than tested against:
 *
 *   AN ALREADY-VISIBLE SELECTION IS NOT RE-CENTRED. ArchitectureGraph's pan
 *   effect only calls setCenter when the node is not fully visible, and the
 *   comment there records why: re-centring on every selection moved the node
 *   out from under the cursor, so the second click of a double-click landed on
 *   the empty pane, which was the real cause of "double-click does not drill"
 *   (comprehension-study S5). So the snap test starts from a node that is
 *   genuinely off-screen, panning the canvas away first if it has to.
 *
 *   DOUBLE-CLICK DRILLS ONLY WHERE THERE IS SOMETHING TO DRILL INTO. The
 *   handler is `comp.children.length > 0 || comp.files.length > 0`, which is
 *   exactly what the node publishes as data-has-children, so the drill test
 *   picks its subject by that attribute rather than by guessing.
 *
 * The two React Flow class selectors used here (.react-flow__node and
 * .react-flow) are framework-published identity, not styling: the node's id and
 * the canvas's box are not available any other way.
 */

import {
  test,
  requireContract,
  expect,
  reportFinding,
  gotoState,
  navigateState,
  readNavState,
  readUrlParams,
  cssEscape,
  waitForInView,
  isFullyInView,
  describeViewport,
  describeObstruction,
  waitForUnoccluded,
  ensureTree,
  ensureDetailPanel,
} from "./fixtures";
import { isAccountedFor, isContentBlob } from "./contract";

/** How long a snap-into-view may take before it has not happened. */
const SNAP_BUDGET_MS = 2_000;

/** Node ids rendered on the canvas right now, in render order. */
async function renderedNodeIds(page: import("@playwright/test").Page): Promise<string[]> {
  return (
    await page
      .locator(".react-flow__node")
      .evaluateAll((els) => els.map((el) => el.getAttribute("data-id") ?? ""))
  ).filter(Boolean);
}

/**
 * Wait, from Node, until the canvas has laid out at least one node.
 *
 * A canvas that never becomes visible is reported with the geometry the app
 * actually left it, not as a bare timeout. The difference matters: "the graph
 * container never became visible" reads as a rendering bug, while "the main
 * content area is 390x0 because the banners above it took the whole viewport"
 * is a layout finding with an obvious owner. The mobile project found exactly
 * that on the first run.
 */
async function waitForGraph(page: import("@playwright/test").Page): Promise<void> {
  try {
    await page.locator(".react-flow").first().waitFor({ state: "visible", timeout: 30_000 });
  } catch {
    const canvas = await page.locator(".react-flow").first().boundingBox().catch(() => null);
    throw new Error(
      `the graph canvas never became visible: it is ` +
        `${canvas ? `${Math.round(canvas.width)}x${Math.round(canvas.height)}px` : "not laid out at all"}; ` +
        `${await describeViewport(page)}`,
    );
  }
  await expect
    .poll(async () => (await renderedNodeIds(page)).length, { timeout: 30_000 , intervals: [100] })
    .toBeGreaterThan(0);
}

/**
 * Drag the canvas by a total offset, in as many drags as it takes.
 *
 * React Flow pans on a mouse drag, and a drag that leaves the pane stops
 * panning, so a travel longer than the pane is split into steps of at most 40
 * percent of it. Used to manufacture the off-screen precondition on a subject
 * whose whole graph fits.
 */
async function panCanvasBy(
  page: import("@playwright/test").Page,
  pane: { x: number; y: number; width: number; height: number },
  dxTotal: number,
  dyTotal: number,
): Promise<void> {
  const maxX = pane.width * 0.4;
  const maxY = pane.height * 0.4;
  let remainingX = dxTotal;
  let remainingY = dyTotal;
  for (let i = 0; i < 12 && (Math.abs(remainingX) > 1 || Math.abs(remainingY) > 1); i++) {
    const stepX = Math.max(-maxX, Math.min(maxX, remainingX));
    const stepY = Math.max(-maxY, Math.min(maxY, remainingY));
    const startX = pane.x + pane.width / 2 - stepX / 2;
    const startY = pane.y + pane.height / 2 - stepY / 2;
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.mouse.move(startX + stepX, startY + stepY, { steps: 12 });
    await page.mouse.up();
    remainingX -= stepX;
    remainingY -= stepY;
  }
}

/** The header controls a reader needs whatever else is on screen. */
const HEADER_CONTROLS = ["lens-select", "semantic-level", "search-button"];

/**
 * Node previews drawn outside the canvas they belong to.
 *
 * Positions are not asserted anywhere else in this spec and are not asserted
 * here either: the claim is containment, not placement. A popup that belongs to
 * a node has no business above the canvas, because what is above the canvas is
 * the header.
 */
async function previewsOutsideCanvas(
  page: import("@playwright/test").Page,
  when: string,
): Promise<string[]> {
  const canvas = await page.locator(".react-flow").first().boundingBox().catch(() => null);
  if (!canvas) return [];
  const previews = page.locator('[data-testid="node-preview"]');
  const out: string[] = [];
  for (let i = 0; i < (await previews.count()); i++) {
    const preview = previews.nth(i);
    const box = await preview.boundingBox().catch(() => null);
    if (!box) continue;
    const id = (await preview.getAttribute("data-component-id")) ?? "an unnamed node";
    if (box.y < canvas.y) {
      out.push(
        `${when}, the preview for ${id} starts ${Math.round(canvas.y - box.y)}px above the ` +
          `canvas top edge, which is where the header is`,
      );
    }
  }
  return out;
}

/**
 * Header controls that will not take a click.
 *
 * Playwright's own actionability check, in trial mode: it does everything a
 * real click does except the click, so an obstructing overlay fails it exactly
 * as it fails a reader. Two seconds, because here a timeout IS the finding.
 */
async function headerNotClickable(
  page: import("@playwright/test").Page,
  when: string,
): Promise<string[]> {
  const out: string[] = [];
  for (const id of HEADER_CONTROLS) {
    const control = page.locator(`[data-testid="${id}"]`).first();
    if ((await control.count()) === 0) continue;
    if (!(await control.isVisible().catch(() => false))) continue;
    try {
      await control.click({ trial: true, timeout: 2_000 });
    } catch {
      out.push(`${when}, the header's ${id} could not be clicked: ${await describeObstruction(page, `[data-testid="${id}"]`)}`);
    }
  }
  return out;
}

// A timeout IS the finding in this spec, so the wait for one is short. Fifteen
// seconds to learn something knowable in five is minutes of nothing happening
// across a run with a dozen such findings, and every wait here stays
// Node-enforced either way. The exhaustive sweeps keep the generous default.
test.use({ actionTimeout: 5_000 });

test.describe("graph", () => {
  test(
    "the root level renders only nodes the projection names",
    { tag: ["@desktop"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      await navigateState(crawlPage, {});
      await waitForGraph(crawlPage);

      const rendered = await renderedNodeIds(crawlPage);
      expect(rendered.length, "the canvas renders at least one node").toBeGreaterThan(0);

      // What legitimately belongs at the root level. A projection with a single
      // root shows that root's CHILDREN rather than the root alone (the graph
      // promotes them; see getVisibleComponents), so both are allowed. An
      // aggregate id is allowed too: it stands for a group of small modules and
      // is the visible trace that replaces silent hiding (P6-4).
      const allowed = new Set<string>(contract.rootIds);
      if (contract.rootIds.length === 1) {
        for (const child of contract.components.get(contract.rootIds[0])?.childIds ?? []) {
          allowed.add(child);
        }
      }
      const aggregateIds = new Set(
        (
          await crawlPage
            .locator('[data-testid="aggregate-node"]')
            .evaluateAll((els) => els.map((el) => el.getAttribute("data-aggregate-id") ?? ""))
        ).filter(Boolean),
      );

      const invented = rendered.filter((id) => !allowed.has(id) && !aggregateIds.has(id));

      // The other direction: what the projection names at the root level has
      // to be on the canvas. Until 2026-09-02 this test checked only that the
      // canvas invented nothing, so a canvas showing one legitimate child of
      // the root and none of the other six passed cleanly, and the most
      // serious defect of the VS Code crawl (571 components, one node) leaked
      // out only sideways through the journey, overview and tour specs.
      //
      // A root is accounted for when it renders. A root that does not render
      // is one the graph promoted (a single root shows its children), and
      // then each child must be a node, a member of a rendered aggregate, or
      // represented by a rendered descendant (the graph unwraps wrappers and
      // promotes hero children). Content blobs are the one deliberate
      // exclusion and are skipped by the same rule the store applies.
      const renderedIds = new Set(rendered);
      const aggregatedIds = new Set<string>();
      for (const members of await crawlPage
        .locator('[data-testid="aggregate-node"]')
        .evaluateAll((els) => els.map((el) => el.getAttribute("data-members") ?? ""))) {
        for (const id of members.split("|")) if (id) aggregatedIds.add(id);
      }
      const missing: string[] = [];
      for (const rootId of contract.rootIds) {
        if (renderedIds.has(rootId) || aggregatedIds.has(rootId)) continue;
        for (const childId of contract.components.get(rootId)?.childIds ?? []) {
          if (isContentBlob(contract, childId)) continue;
          if (!isAccountedFor(contract, childId, renderedIds, aggregatedIds)) {
            missing.push(childId);
          }
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description:
          `${rendered.length} node(s) at the root level, ${aggregateIds.size} of them aggregates`,
      });
      reportFinding("graph.invented_node", invented, {
        title: "graph nodes the projection does not name",
      });
      reportFinding("graph.missing_node", missing, {
        title: "root-level components the projection names that the canvas does not account for",
      });
      expect(
        invented,
        "graph nodes the projection does not name (the canvas inventing structure)",
      ).toEqual([]);
      expect(
        missing,
        "root-level components the projection names that the canvas neither renders, " +
          "aggregates, nor represents by a descendant",
      ).toEqual([]);
    },
  );

  test(
    "clicking a node selects it, clicking the pane clears it",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      await navigateState(crawlPage, {});
      await waitForGraph(crawlPage);

      const clickDead: string[] = [];
      const paneNoClear: string[] = [];
      const occluded: string[] = [];

      // A component node, not an aggregate: aggregates handle their own
      // expand/collapse and are deliberately not selectable (P6-4), so
      // expecting a selection from one would be testing a promise the product
      // does not make.
      const nodes = crawlPage.locator('[data-testid="graph-node"]');
      const nodeCount = await nodes.count();
      expect(nodeCount, "the canvas renders at least one component node").toBeGreaterThan(0);

      // Before anything is clicked: is every node on this level actually
      // VISIBLE, or is the app's own chrome painted over it? Geometry says the
      // node is in the canvas; only hit testing says the reader can see it, and
      // on a phone the drill hint, the breadcrumb bar and the detail sheet all
      // share the canvas's corners with the nodes.
      const renderedIds = await nodes.evaluateAll((els) =>
        els.map((el) => el.getAttribute("data-component-id") ?? ""),
      );
      for (const id of renderedIds) {
        if (!id) continue;
        const result = await waitForUnoccluded(
          crawlPage,
          `[data-testid="graph-node"][data-component-id="${cssEscape(id)}"]`,
          SNAP_BUDGET_MS,
        );
        if (result.occluded) {
          occluded.push(
            `node ${id}'s centre is still covered by ${result.lastCover} after ` +
              `${result.coveredForMs}ms (${await describeViewport(crawlPage)})`,
          );
        }
      }

      const targetId = await nodes.first().getAttribute("data-component-id");
      expect(targetId, "the first graph node publishes a component id").toBeTruthy();

      await nodes.first().click({ timeout: 5_000  });

      // Poll the beacon rather than reading it once: selection, the detail
      // panel mount and the graph's own re-paint are separate React updates,
      // and reading between them would report a transient frame as a defect
      // (the mistake search.spec.ts records).
      await expect
        .poll(async () => (await readNavState(crawlPage)).selected, { timeout: 10_000 , intervals: [100] })
        .toBe(targetId)
        .catch(() => {});

      const afterClick = await readNavState(crawlPage);
      if (afterClick.selected !== targetId) {
        clickDead.push(
          `clicking node ${targetId} left the beacon's selection at "${afterClick.selected}"`,
        );
      }
      // The visible half of the same claim, twice over: React Flow's own
      // selected class, and the node's published data-selected.
      const selectedClass = await crawlPage
        .locator(`.react-flow__node[data-id="${cssEscape(targetId ?? "")}"]`)
        .first()
        .getAttribute("class");
      if (!(selectedClass ?? "").split(/\s+/).includes("selected")) {
        clickDead.push(`node ${targetId} is selected in the store but carries no selected class`);
      }
      await ensureDetailPanel(crawlPage);
      await expect
        .poll(
          async () =>
            crawlPage
              .locator('[data-testid="detail-panel"]')
              .first()
              .getAttribute("data-component-id")
              .catch(() => null),
          { timeout: 10_000, intervals: [100] },
        )
        .toBe(targetId)
        .catch(() => {});
      const panelId = await crawlPage
        .locator('[data-testid="detail-panel"]')
        .first()
        .getAttribute("data-component-id")
        .catch(() => null);
      if (panelId !== targetId) {
        clickDead.push(
          `clicking node ${targetId} opened a detail panel for "${panelId ?? "nothing"}"`,
        );
      }

      // Clicking the empty pane clears the selection. Aimed at a corner of the
      // canvas, which is where the layout is least likely to have put a node.
      const canvasBox = await crawlPage.locator(".react-flow__pane").first().boundingBox();
      if (canvasBox) {
        await crawlPage.mouse.click(canvasBox.x + 8, canvasBox.y + canvasBox.height - 8);
      }
      await expect
        .poll(async () => (await readNavState(crawlPage)).selected, { timeout: 10_000 , intervals: [100] })
        .toBe("")
        .catch(() => {});

      const afterPane = await readNavState(crawlPage);
      if (afterPane.selected !== "") {
        paneNoClear.push(
          `clicking the empty pane left the beacon's selection at "${afterPane.selected}"`,
        );
      }
      if ((await crawlPage.locator('[data-testid="detail-panel"]').count()) > 0) {
        paneNoClear.push("clicking the empty pane left the detail panel on screen");
      }

      test.info().annotations.push({
        type: "coverage",
        description: `node click and pane clear exercised on ${targetId} (${nodeCount} nodes at this level)`,
      });
      reportFinding("graph.click_dead", clickDead, {
        title: "graph nodes whose click does not select what it names",
      });
      reportFinding("graph.pane_no_clear", paneNoClear, {
        title: "an empty-pane click that does not clear the selection",
      });
      reportFinding("graph.node_occluded", occluded, {
        title: "graph nodes on the canvas with something else painted over them",
      });
      expect(clickDead, "graph nodes whose click does not select what it names").toEqual([]);
      expect(paneNoClear, "an empty-pane click that does not clear the selection").toEqual([]);
      expect(
        occluded,
        "graph nodes the reader cannot see because something is painted over them",
      ).toEqual([]);
    },
  );

  test(
    "selecting an off-screen component brings its node into view",
    { tag: ["@desktop"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      await navigateState(crawlPage, {});
      await waitForGraph(crawlPage);

      const nodeIds = (
        await crawlPage
          .locator('[data-testid="graph-node"]')
          .evaluateAll((els) => els.map((el) => el.getAttribute("data-component-id") ?? ""))
      ).filter(Boolean);
      if (nodeIds.length === 0) {
        test.info().annotations.push({
          type: "coverage",
          description: "skipped: no component nodes at the root level to snap to",
        });
      }
      test.skip(nodeIds.length === 0, "no component nodes at the root level to snap to");

      const nodeSelectorFor = (id: string) =>
        `.react-flow__node[data-id="${cssEscape(id)}"]`;

      // Find a node that is NOT already fully visible. The app deliberately
      // does not re-centre a visible selection, so starting from one would be
      // asserting the opposite of the documented behaviour.
      //
      // A node bigger than the canvas is no good either: nothing can bring it
      // fully into view, so it would fail the assertion for a reason that is
      // not the claim. Only nodes that could fit are eligible.
      const canvasBox = await crawlPage.locator(".react-flow").first().boundingBox();
      const findOffscreenTarget = async (): Promise<string | null> => {
        for (const id of nodeIds) {
          if (await isFullyInView(crawlPage, nodeSelectorFor(id))) continue;
          const node = await crawlPage.locator(nodeSelectorFor(id)).first().boundingBox();
          if (!node || !canvasBox) continue;
          if (node.width > canvasBox.width || node.height > canvasBox.height) continue;
          return id;
        }
        return null;
      };

      let target = await findOffscreenTarget();
      let how = "already off-screen";

      const pane = await crawlPage.locator(".react-flow__pane").first().boundingBox();
      if (!target && pane) {
        // Everything fits. Pan the canvas so something leaves it, then pick
        // again: manufacturing the precondition is honest, asserting on a
        // precondition that does not hold is not.
        //
        // The distance is derived from the canvas, not a fixed 900x700 that
        // happened to be enough once. A drag has to stay inside the pane, so
        // 1.5 canvases of travel is several shorter drags.
        await panCanvasBy(crawlPage, pane, -pane.width * 1.5, -pane.height * 1.5);
        target = await findOffscreenTarget();
        how = "panned 1.5 canvases away";
      }

      let zoomSteps = 0;
      if (!target) {
        // A graph small enough to survive that pan (React Flow re-fits a single
        // centred node) still has to yield the precondition. Zoom in with the
        // app's own control until a node no longer fits.
        const zoomIn = crawlPage.locator(".react-flow__controls-zoomin");
        while (!target && zoomSteps < 8 && (await zoomIn.count()) > 0) {
          await zoomIn.first().click({ timeout: 5_000 });
          zoomSteps++;
          target = await findOffscreenTarget();
        }
        if (target) how = `zoomed in ${zoomSteps} step(s)`;
      }

      if (!target) {
        test.info().annotations.push({
          type: "coverage",
          description:
            `skipped: no node could be put off-screen on this subject; ` +
            `${nodeIds.length} node(s), panned 1.5 canvases and zoomed in ${zoomSteps} step(s) ` +
            `and every one still fits inside the canvas`,
        });
      }
      test.skip(!target, "no node could be put off-screen, by panning or by zooming in");

      const id = target as string;
      // Selected from the TREE, not the canvas: a click on a node the reader
      // cannot see is not a gesture anybody makes, and the tree row is the
      // route search results, deep links and tours all end up taking.
      await ensureTree(crawlPage);
      const row = crawlPage.locator(
        `[data-testid="tree-node"][data-component-id="${cssEscape(id)}"]`,
      );
      if ((await row.count()) === 0) {
        test.info().annotations.push({
          type: "coverage",
          description: `skipped: ${id} is on the canvas but has no tree row to select it from`,
        });
      }
      test.skip((await row.count()) === 0, `no tree row for ${id} to select from`);
      await row.first().click({ timeout: 5_000  });

      const arrived = await waitForInView(crawlPage, nodeSelectorFor(id), SNAP_BUDGET_MS);
      const noSnap = arrived
        ? []
        : [`${id} was selected from the tree and its node never came fully into view`];

      test.info().annotations.push({
        type: "coverage",
        description: `snap-into-view checked on ${id} (${how}) within ${SNAP_BUDGET_MS}ms`,
      });
      reportFinding("graph.no_snap", noSnap, {
        title: "selections that never bring their node into view",
      });
      expect(
        noSnap,
        `selecting an off-screen component must bring its node fully inside the canvas ` +
          `within ${SNAP_BUDGET_MS}ms, or the reader is told they selected something ` +
          `they cannot see`,
      ).toEqual([]);
    },
  );

  test(
    "double-clicking a node with children drills into it, and Home comes back",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      await navigateState(crawlPage, {});
      await waitForGraph(crawlPage);

      const drillDead: string[] = [];
      const wrongChildren: string[] = [];
      const homeDead: string[] = [];

      // Chosen by the node's own data-has-children, which publishes exactly the
      // predicate the drill handler uses. Guessing from the manifest would pick
      // a node the canvas may have aggregated away.
      const candidates = crawlPage.locator(
        '[data-testid="graph-node"][data-has-children="true"]',
      );
      test.skip(
        (await candidates.count()) === 0,
        "no node at the root level has anything to drill into",
      );
      const targetId = (await candidates.first().getAttribute("data-component-id")) ?? "";

      await candidates.first().dblclick({ timeout: 5_000  });

      await expect
        .poll(async () => (await readNavState(crawlPage)).drill, { timeout: 15_000 , intervals: [100] })
        .toBe(targetId)
        .catch(() => {});

      const drilled = await readNavState(crawlPage);
      if (drilled.drill !== targetId) {
        drillDead.push(
          `double-clicking ${targetId} left the beacon's drill at "${drilled.drill}"`,
        );
      }
      const params = await readUrlParams(crawlPage);
      if (params.get("drill") !== targetId) {
        drillDead.push(
          `drilling into ${targetId} left the URL carrying drill="${params.get("drill") ?? ""}"`,
        );
      }
      const crumbs = (
        await crawlPage
          .locator('[data-testid="breadcrumb-item"]')
          .evaluateAll((els) => els.map((el) => el.getAttribute("data-component-id") ?? ""))
      ).filter(Boolean);
      if (crumbs[crumbs.length - 1] !== targetId) {
        drillDead.push(
          `after drilling into ${targetId} the breadcrumbs end at "${
            crumbs[crumbs.length - 1] ?? "nothing"
          }"`,
        );
      }
      if ((await crawlPage.locator('[data-testid="drill-home"]').count()) === 0) {
        drillDead.push(`drilling into ${targetId} offered no Home button to get back`);
      }

      // Only this component's children (or aggregates standing for some of
      // them) may render at this level. A node from somewhere else appearing
      // here is the level lying about where the reader is.
      if (drilled.drill === targetId) {
        await waitForGraph(crawlPage).catch(() => {});
        const rendered = await renderedNodeIds(crawlPage);
        const aggregateIds = new Set(
          (
            await crawlPage
              .locator('[data-testid="aggregate-node"]')
              .evaluateAll((els) => els.map((el) => el.getAttribute("data-aggregate-id") ?? ""))
          ).filter(Boolean),
        );
        const children = new Set(contract.components.get(targetId)?.childIds ?? []);
        const strangers = rendered.filter((id) => !children.has(id) && !aggregateIds.has(id));
        if (strangers.length) {
          wrongChildren.push(
            `drilling into ${targetId} rendered ${strangers.length} node(s) that are not its ` +
              `children, first ${strangers[0]}`,
          );
        }
      }

      // Home. The affordance the app offers, so the route tested is the route
      // taken; the design's reset probe uses the same one.
      const home = crawlPage.locator('[data-testid="drill-home"]');
      if ((await home.count()) > 0) {
        await home.first().click({ timeout: 5_000  });
      }
      await expect
        .poll(async () => (await readNavState(crawlPage)).drill, { timeout: 10_000 , intervals: [100] })
        .toBe("")
        .catch(() => {});

      const homed = await readNavState(crawlPage);
      if (homed.drill !== "") {
        homeDead.push(`Home left the beacon's drill at "${homed.drill}"`);
      }
      if ((await crawlPage.locator('[data-testid="breadcrumb-item"]').count()) > 0) {
        homeDead.push("Home left breadcrumbs on screen");
      }
      if ((await crawlPage.locator('[data-testid="drill-home"]').count()) > 0) {
        homeDead.push("Home is still offered after going Home");
      }
      const homeParams = await readUrlParams(crawlPage);
      // Same allowance as the reset probe: `data` and `mode` address the thing
      // being looked at, and `lens` is not drill state.
      const leftovers = [...homeParams.keys()].filter(
        (k) => k !== "data" && k !== "lens" && k !== "mode",
      );
      if (leftovers.length) {
        homeDead.push(`Home left the URL carrying ${leftovers.join(", ")}`);
      }

      test.info().annotations.push({
        type: "coverage",
        description: `drill and Home exercised on ${targetId}`,
      });
      reportFinding("graph.drill_dead", drillDead, {
        title: "double-clicks that do not drill where they say they do",
      });
      reportFinding("graph.drill_wrong_children", wrongChildren, {
        title: "drill levels that render nodes belonging somewhere else",
      });
      reportFinding("graph.home_dead", homeDead, {
        title: "Home that does not return the reader to the top",
      });
      expect(drillDead, "double-clicks that do not drill where they say they do").toEqual([]);
      expect(wrongChildren, "drill levels that render nodes belonging somewhere else").toEqual([]);
      expect(homeDead, "Home that does not return the reader to the top").toEqual([]);
    },
  );
  test(
    "the hover preview stays inside the canvas and never covers the header",
    { tag: ["@desktop"] },
    async ({ crawlPage }) => {
      await requireContract(crawlPage);
      // The exploratory pass found this and no assertion could see it: arriving
      // in the workbench from an Overview question leaves the pointer over the
      // single centred root node, its preview opens with no gesture behind it,
      // and the fixed-position popup is drawn over the lens switcher, the level
      // toggle, Review and part of Search. Every header click timed out on
      // obstruction. So the case asserts both halves: nothing that belongs to
      // the canvas is drawn above the canvas, and the header still takes a
      // click.
      const covering: string[] = [];

      // 1. Arrive the way a reader does, and do not move the pointer
      //    afterwards: the whole point is a preview nobody asked for.
      await gotoState(crawlPage, { mode: "overview" });
      const direction = crawlPage.locator(
        '[data-testid="overview-direction"][data-direction="questions"]',
      );
      if ((await direction.count()) > 0) {
        await direction.first().click({ timeout: 5_000 }).catch(() => {});
        const route = crawlPage.locator('[data-testid="question-route"][data-available="true"]');
        if ((await route.count()) > 0) {
          const routeId = await route.first().getAttribute("data-route-id");
          await route.first().click({ timeout: 5_000 }).catch(() => {});
          const go = crawlPage.locator(
            `[data-testid="question-route-continue"][data-route-id="${cssEscape(routeId ?? "")}"]`,
          );
          if ((await go.count()) > 0) await go.first().click({ timeout: 5_000 }).catch(() => {});
        }
      }
      await expect
        .poll(async () => (await readNavState(crawlPage)).mode, { timeout: 20_000, intervals: [100] })
        .toBe("workbench")
        .catch(() => {});
      if ((await readNavState(crawlPage)).mode !== "workbench") {
        await navigateState(crawlPage, {});
      }
      await waitForGraph(crawlPage);
      // A preview that opened without pointer movement takes the 400ms hover
      // delay to appear, so give it that long to show itself before deciding
      // nothing is there.
      await crawlPage
        .locator('[data-testid="node-preview"]')
        .first()
        .waitFor({ state: "visible", timeout: 2_000 })
        .catch(() => {});
      covering.push(...(await previewsOutsideCanvas(crawlPage, "on arriving from a question route")));
      covering.push(...(await headerNotClickable(crawlPage, "on arriving from a question route")));

      // 2. The same node, hovered deliberately. The arrival case depends on
      //    where the pointer happened to be; this one does not.
      const node = crawlPage.locator('[data-testid="graph-node"]').first();
      expect(await node.count(), "the canvas renders at least one component node").toBeGreaterThan(0);
      const hoveredId = await node.getAttribute("data-component-id");
      await node.hover({ timeout: 5_000 }).catch(() => {});
      const preview = crawlPage.locator('[data-testid="node-preview"]');
      await preview.first().waitFor({ state: "visible", timeout: 2_000 }).catch(() => {});
      const opened = (await preview.count()) > 0;
      covering.push(...(await previewsOutsideCanvas(crawlPage, `while hovering ${hoveredId}`)));
      covering.push(...(await headerNotClickable(crawlPage, `while hovering ${hoveredId}`)));

      test.info().annotations.push({
        type: "coverage",
        description:
          `hover preview checked on arrival and on a deliberate hover of ${hoveredId}` +
          (opened ? "" : "; the node carries no documentation, so no preview opened on hover"),
      });
      reportFinding("graph.preview_covers_header", covering, {
        title: "hover previews drawn outside the canvas, over the controls",
      });
      expect(
        covering,
        "hover previews drawn outside the canvas, over the header controls",
      ).toEqual([]);
    },
  );
});
