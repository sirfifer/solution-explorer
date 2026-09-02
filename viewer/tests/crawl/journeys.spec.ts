/**
 * Journeys: walk a path a reader would walk, then prove nothing of it survived.
 *
 * This is the spec the owner asked for by name. The defect class is not "a
 * button does not work"; it is that you drill into a context, do something in
 * it, go back to the start, and something from the old context is still in
 * force. It survives every kind of testing that looks at one screen at a time,
 * because on each individual screen everything is fine. It shows up as the NEXT
 * thing you click behaving strangely, and by then nobody connects it to the
 * journey that caused it.
 *
 * So every journey here ends the same way: resetProbe (see fixtures.ts) returns
 * to the start the way a reader would, Home then Escape, and then asserts on
 * both the app's own account of where it is (the beacon) and what is actually
 * on screen and in the URL. Residue is reported as `journey.context_leak`
 * naming the journey that left it, because "something leaked" is not
 * actionable and "J4 left capability=cap:x in the URL" is.
 *
 * The journeys are numbered as the design numbers them so a finding and the
 * design can be read side by side.
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
  navFields,
  resetProbe,
  cssEscape,
  waitForStableBox,
  describeViewport,
  describeObstruction,
  waitForBoot,
  ensureTree,
  visibleEntry,
} from "./fixtures";
import { pathToDeepest } from "./contract";

/** Lens-scoped selection: the beacon field and URL param each lens owns. */
type SelectionField = "capability" | "entity" | "rule" | "finding";
const LENS_SELECTION: Record<string, { field: SelectionField; param: string }> = {
  capability: { field: "capability", param: "capability" },
  data: { field: "entity", param: "entity" },
  rules: { field: "rule", param: "rule" },
  design: { field: "finding", param: "finding" },
};

/** Every URL param a lens-scoped selection can leave behind. */
const LENS_PARAMS = ["capability", "entity", "rule", "finding", "flow", "step"];

// A timeout IS the finding in this spec, so the wait for one is short. Fifteen
// seconds to learn something knowable in five is minutes of nothing happening
// across a run with a dozen such findings, and every wait here stays
// Node-enforced either way. The exhaustive sweeps keep the generous default.
test.use({ actionTimeout: 5_000 });

test.describe("journeys", () => {
  test(
    "J1: drilling to the bottom and coming back leaves nothing behind",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      const chain = pathToDeepest(contract);
      test.skip(chain.length < 2, "the projection is one level deep; there is nothing to drill");

      // Every element except the last: the last is the deepest component, and
      // drilling into a leaf shows an empty level, which is the app's own
      // documented behaviour rather than a defect.
      const hops = chain.slice(0, -1);
      const wrong: string[] = [];

      await navigateState(crawlPage, {});
      for (const hop of hops) {
        // The canvas is the gesture under test, so the node is preferred. It is
        // legitimately unavailable when the level aggregated this component
        // away or the node budget dropped it, and the tree row is then the same
        // navigation by the route a reader would actually have (the design's
        // own fallback).
        const node = crawlPage.locator(
          `[data-testid="graph-node"][data-component-id="${cssEscape(hop.id)}"]`,
        );
        // The previous hop's drill has landed on the beacon before the new
        // level's nodes have rendered, so the node is polled for briefly
        // rather than read once; a level that never renders it falls back to
        // the tree below. Node-enforced and bounded, like every other wait.
        const nodeRendered = await expect
          .poll(() => node.count(), { timeout: 2_000, intervals: [100] })
          .toBeGreaterThan(0)
          .then(() => true)
          .catch(() => false);
        // A single root whose children ARE the top level is not a hop. The
        // graph promotes such a root (store.ts flattenTopLevel), so the level
        // the reader starts on is already the root's and drilling into it
        // would show the same nodes. It has no node and no tree row by design;
        // the walk continues from its children. Decided after the poll above:
        // read once, a root that simply had not rendered yet was skipped and
        // its child then looked for at the wrong level (UnaMentis, 2026-09-02).
        if (
          contract.rootIds.length === 1
          && hop.id === contract.rootIds[0]
          && !nodeRendered
          && (await readNavState(crawlPage)).drill === ""
        ) {
          continue;
        }
        let via = "node";
        if (nodeRendered) {
          // Wait for the node to stop moving first. The previous hop's re-layout
          // is still animating, and a node that travels between the two presses
          // takes the second one somewhere else; see waitForStableBox.
          const nodeSelector =
            `[data-testid="graph-node"][data-component-id="${cssEscape(hop.id)}"]`;
          const settled = await waitForStableBox(crawlPage, nodeSelector);
          if (!settled) {
            wrong.push(
              `${hop.id}: its node never stopped moving, so a double-click cannot land ` +
                `(${await describeViewport(crawlPage)})`,
            );
          }
          await node.first().dblclick({ timeout: 5_000  }).catch(() => {});
        } else {
          via = "tree";
          await ensureTree(crawlPage);
          const row = crawlPage.locator(
            `[data-testid="tree-node"][data-component-id="${cssEscape(hop.id)}"]`,
          );
          if ((await row.count()) === 0) {
            wrong.push(`${hop.id}: neither a graph node nor a tree row to drill from`);
            break;
          }
          await row.first().dblclick({ timeout: 5_000  }).catch(() => {});
          // A tree double-click may only select. Fall back to the URL route,
          // which is the same store transition by a different door.
          if ((await readNavState(crawlPage)).drill !== hop.id) {
            await navigateState(crawlPage, { drill: hop.id });
          }
        }

        await expect
          .poll(async () => (await readNavState(crawlPage)).drill, { timeout: 15_000 , intervals: [100] })
          .toBe(hop.id)
          .catch(() => {});

        let state = await readNavState(crawlPage);
        if (state.drill !== hop.id && via === "node") {
          // Recorded, then carried on by URL. The double-click is a real
          // gesture and a real finding when it does not drill, but abandoning
          // the descent here would mean the rest of the journey, and the reset
          // probe it exists to feed, are never exercised at all.
          wrong.push(
            `hop to ${hop.id} (depth ${hop.depth}) by double-clicking its node left the drill ` +
              `at "${state.drill}" (${await describeViewport(crawlPage)})`,
          );
          await navigateState(crawlPage, { drill: hop.id });
          await expect
            .poll(async () => (await readNavState(crawlPage)).drill, { timeout: 15_000 , intervals: [100] })
            .toBe(hop.id)
            .catch(() => {});
          state = await readNavState(crawlPage);
        }
        if (state.drill !== hop.id) {
          wrong.push(
            `hop to ${hop.id} (depth ${hop.depth}, via ${via}) left the drill at "${state.drill}"`,
          );
          break;
        }
        const params = await readUrlParams(crawlPage);
        if (params.get("drill") !== hop.id) {
          wrong.push(
            `hop to ${hop.id} left the URL carrying drill="${params.get("drill") ?? ""}"`,
          );
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description:
          `J1 drilled ${hops.length} level(s) to depth ${chain[chain.length - 1].depth}: ` +
          hops.map((h) => h.id).join(" > "),
      });

      reportFinding("journey.drill_hop", wrong, {
        title: "drill hops that did not land where they said they would",
      });
      const residue = await resetProbe(crawlPage, "J1 drill to the bottom");
      reportFinding("journey.context_leak", residue, {
        title: "state that survived a journey's reset",
      });
      expect(wrong, "drill hops that did not land where they said they would").toEqual([]);
      expect(residue, "state that survived J1's reset").toEqual([]);
    },
  );

  test(
    "J2: browser back steps out one level at a time, and forward re-applies",
    { tag: ["@desktop"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      const chain = pathToDeepest(contract);
      const hops = chain.slice(0, -1);
      test.skip(hops.length < 2, "fewer than two drill levels; back/forward has nothing to walk");

      // Descend by URL. Each drill change pushes a history entry (useUrlSync
      // pushes for a drill change and replaces for everything else), which is
      // exactly the history stack this test then walks back up.
      await navigateState(crawlPage, {});
      for (const hop of hops) {
        await navigateState(crawlPage, { drill: hop.id });
        await expect
          .poll(async () => (await readNavState(crawlPage)).drill, { timeout: 15_000 , intervals: [100] })
          .toBe(hop.id)
          .catch(() => {});
      }

      const backWrong: string[] = [];
      const forwardWrong: string[] = [];

      // Back once per hop, expecting the drill to be the PREVIOUS hop each time
      // and empty after the last step out.
      for (let i = hops.length - 1; i >= 0; i--) {
        const expected = i === 0 ? "" : hops[i - 1].id;
        await crawlPage.goBack({ timeout: 30_000  }).catch(() => {});
        await expect
          .poll(async () => (await readNavState(crawlPage)).drill, { timeout: 15_000 , intervals: [100] })
          .toBe(expected)
          .catch(() => {});
        const state = await readNavState(crawlPage);
        if (state.drill !== expected) {
          backWrong.push(
            `back from ${hops[i].id} left the drill at "${state.drill}", expected ` +
              `"${expected || "(top)"}"`,
          );
          break;
        }
        const params = await readUrlParams(crawlPage);
        if ((params.get("drill") ?? "") !== expected) {
          backWrong.push(
            `back from ${hops[i].id} left the URL at drill="${params.get("drill") ?? ""}", ` +
              `expected "${expected}"`,
          );
        }
      }

      // Forward once: it must re-apply exactly the level back just left.
      if (backWrong.length === 0) {
        await crawlPage.goForward({ timeout: 30_000  }).catch(() => {});
        await expect
          .poll(async () => (await readNavState(crawlPage)).drill, { timeout: 15_000 , intervals: [100] })
          .toBe(hops[0].id)
          .catch(() => {});
        const state = await readNavState(crawlPage);
        if (state.drill !== hops[0].id) {
          forwardWrong.push(
            `forward left the drill at "${state.drill}", expected "${hops[0].id}"; the ` +
              `forward stack is the thing a popstate handler that writes the URL destroys`,
          );
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description: `J2 walked ${hops.length} level(s) back and one forward`,
      });
      reportFinding("journey.back_wrong", backWrong, {
        title: "browser back that does not step out exactly one level",
      });
      reportFinding("journey.forward_wrong", forwardWrong, {
        title: "browser forward that does not re-apply the level it left",
      });
      const residue = await resetProbe(crawlPage, "J2 back and forward");
      reportFinding("journey.context_leak", residue, {
        title: "state that survived a journey's reset",
      });
      expect(backWrong, "browser back that does not step out one level at a time").toEqual([]);
      expect(forwardWrong, "browser forward that does not re-apply the level").toEqual([]);
      expect(residue, "state that survived J2's reset").toEqual([]);
    },
  );

  test(
    "J3: a lens round trip never drops the selection",
    { tag: ["@desktop"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      // Invariant I12, stated in the store: switching lens preserves selection,
      // breadcrumbs, drill level and URL state. It is the invariant that makes
      // lenses feel like views of one thing rather than eight separate apps,
      // and it is invisible until it breaks.
      const lenses = contract.lensesExpected.filter((id) => id !== "structure");
      test.skip(lenses.length === 0, "only the structure lens is warranted; nothing to round trip");

      const target = [...contract.components.values()].find((c) => c.depth === 0)
        ?? [...contract.components.values()][0];
      test.skip(!target, "no component to select");

      await navigateState(crawlPage, { component: target.id });
      await expect
        .poll(async () => (await readNavState(crawlPage)).selected, { timeout: 20_000 , intervals: [100] })
        .toBe(target.id)
        .catch(() => {});

      const dropped: string[] = [];
      const select = crawlPage.locator('[data-testid="lens-select"]');
      test.skip((await select.count()) === 0, "no lens switcher in this build");

      for (const lens of [...lenses, "structure"]) {
        try {
          await select.first().selectOption(lens, { timeout: 20_000  });
          await expect
            .poll(async () => (await readNavState(crawlPage)).lens, { timeout: 20_000 , intervals: [100] })
            .toBe(lens)
            .catch(() => {});
          const state = await readNavState(crawlPage);
          if (state.lens !== lens) {
            dropped.push(`the switcher would not enter the ${lens} lens (stayed on ${state.lens})`);
            continue;
          }
          if (state.selected !== target.id) {
            dropped.push(
              `switching to the ${lens} lens changed the selection from ${target.id} to ` +
                `"${state.selected}" (invariant I12 says a lens switch preserves it)`,
            );
          }
        } catch (err) {
          dropped.push(`${lens}: ${(err as Error).message.split("\n")[0]}`);
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description: `J3 round-tripped ${lenses.length} lens(es) holding ${target.id} selected`,
      });
      reportFinding("journey.lens_dropped_selection", dropped, {
        title: "lens switches that lose the reader's selection",
      });
      const residue = await resetProbe(crawlPage, "J3 lens round trip");
      reportFinding("journey.context_leak", residue, {
        title: "state that survived a journey's reset",
      });
      expect(dropped, "lens switches that lose the reader's selection").toEqual([]);
      expect(residue, "state that survived J3's reset").toEqual([]);
    },
  );

  test(
    "J4: a lens-scoped selection sets its own state and leaves none behind",
    { tag: ["@desktop"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      const rowLenses = contract.lensesExpected.filter(
        (id) => id in LENS_SELECTION || id === "flow",
      );
      test.skip(rowLenses.length === 0, "no lens with selectable rows is warranted");

      const rowDead: string[] = [];
      const paramLeak: string[] = [];
      const exercised: string[] = [];

      for (const lens of rowLenses) {
        try {
          await navigateState(crawlPage, { lens });
          await expect
            .poll(async () => (await readNavState(crawlPage)).lens, { timeout: 30_000 , intervals: [100] })
            .toBe(lens)
            .catch(() => {});
          if ((await readNavState(crawlPage)).lens !== lens) {
            rowDead.push(`the ${lens} lens could not be entered by URL`);
            continue;
          }

          if (lens === "flow") {
            const entry = crawlPage.locator('[data-testid="flow-entry"]');
            if ((await entry.count()) === 0) {
              rowDead.push("the flow lens offers no entry flow to follow");
              continue;
            }
            const flowId = (await entry.first().getAttribute("data-flow-id")) ?? "";
            // Bidirectional: the entry the panel offers must be a flow-bearing
            // component the data actually names. The panel's own RANKING is not
            // asserted; see readLensRowIds for why.
            const warranted = contract.lensRowIds.get("flow") ?? [];
            if (!warranted.includes(flowId)) {
              rowDead.push(`flow entry "${flowId}" is not a flow-bearing component in the data`);
            }
            await entry.first().click({ timeout: 5_000  });
            await expect
              .poll(async () => (await readNavState(crawlPage)).flow, { timeout: 15_000 , intervals: [100] })
              .toBe(flowId)
              .catch(() => {});

            const entered = await readNavState(crawlPage);
            if (entered.flow !== flowId) {
              rowDead.push(`clicking flow entry ${flowId} left the beacon's flow at "${entered.flow}"`);
              continue;
            }
            if (entered.selected === "") {
              rowDead.push(`following flow ${flowId} selected no component`);
            }
            if ((await readUrlParams(crawlPage)).get("flow") !== flowId) {
              rowDead.push(`following flow ${flowId} did not put it in the URL`);
            }

            // Step forward and back. The step index is the walk's "where am I",
            // and it rides in the URL only above zero (buildUrl omits step=0),
            // so the URL is checked only where the app promises to write it.
            const next = crawlPage.locator('[data-testid="flow-next"]');
            if ((await next.count()) > 0 && (await next.first().isEnabled())) {
              await next.first().click({ timeout: 5_000  });
              await expect
                .poll(async () => (await readNavState(crawlPage)).flowStep, { timeout: 10_000 , intervals: [100] })
                .toBe("1")
                .catch(() => {});
              const stepped = await readNavState(crawlPage);
              if (stepped.flowStep !== "1") {
                rowDead.push(`flow ${flowId}: Next left the step at "${stepped.flowStep}"`);
              } else if ((await readUrlParams(crawlPage)).get("step") !== "1") {
                rowDead.push(`flow ${flowId}: step 1 is not carried in the URL`);
              }
              const prev = crawlPage.locator('[data-testid="flow-prev"]');
              if ((await prev.count()) > 0) {
                await prev.first().click({ timeout: 5_000  });
                await expect
                  .poll(async () => (await readNavState(crawlPage)).flowStep, { timeout: 10_000 , intervals: [100] })
                  .toBe("0")
                  .catch(() => {});
                const back = await readNavState(crawlPage);
                if (back.flowStep !== "0") {
                  rowDead.push(`flow ${flowId}: Previous left the step at "${back.flowStep}"`);
                }
              }
            }
            exercised.push("flow");
          } else {
            const spec = LENS_SELECTION[lens];
            const rows = crawlPage.locator(
              `[data-testid="lens-row"][data-lens="${lens}"]`,
            );
            if ((await rows.count()) === 0) {
              rowDead.push(`the ${lens} lens is warranted but its panel offers no rows`);
              continue;
            }
            const rowId = (await rows.first().getAttribute("data-row-id")) ?? "";
            const warranted = contract.lensRowIds.get(lens) ?? [];
            if (!warranted.includes(rowId)) {
              rowDead.push(`${lens} row "${rowId}" is not named anywhere in the data`);
            }
            try {
              await rows.first().click({ timeout: 5_000  });
            } catch (clickErr) {
              // A click that never becomes possible is usually not about the
              // row. Measure what is actually sitting on it, and what the app
              // left the panel to work in, so the finding names a cause rather
              // than a timeout.
              const obstruction = await describeObstruction(
                crawlPage,
                `[data-testid="lens-row"][data-lens="${lens}"]`,
              ).catch(() => "the obstruction could not be measured");
              const panelBox = await crawlPage
                .locator(`[data-testid="lens-panel"][data-lens="${lens}"]`)
                .first()
                .boundingBox()
                .catch(() => null);
              rowDead.push(
                `${lens} row "${rowId}" would not accept a click ` +
                  `(${(clickErr as Error).message.split("\n")[0]}): ${obstruction}. The panel is ` +
                  `${panelBox ? `${Math.round(panelBox.width)}x${Math.round(panelBox.height)}px` : "unmeasurable"}; ` +
                  `${await describeViewport(crawlPage)}`,
              );
              continue;
            }
            await expect
              .poll(async () => (await readNavState(crawlPage))[spec.field] as string, { timeout: 15_000 , intervals: [100] })
              .toBe(rowId)
              .catch(() => {});

            const picked = await readNavState(crawlPage);
            if (picked[spec.field] !== rowId) {
              rowDead.push(
                `clicking ${lens} row ${rowId} left the beacon's ${spec.field} at ` +
                  `"${picked[spec.field]}"`,
              );
              continue;
            }
            // Selecting a row selects its owning component too: stable identity
            // (I12) is what makes a row and a node the same thing.
            if (picked.selected === "") {
              rowDead.push(`selecting ${lens} row ${rowId} selected no owning component`);
            }
            if ((await readUrlParams(crawlPage)).get(spec.param) !== rowId) {
              rowDead.push(`selecting ${lens} row ${rowId} did not put it in the URL`);
            }
            exercised.push(lens);
          }

          // Back to structure. Every lens-scoped param rides only under its own
          // lens (see buildUrl), so leaving the lens must leave none of them.
          await crawlPage
            .locator('[data-testid="lens-select"]')
            .first()
            .selectOption("structure", { timeout: 20_000  })
            .catch(() => {});
          await expect
            .poll(async () => (await readNavState(crawlPage)).lens, { timeout: 20_000 , intervals: [100] })
            .toBe("structure")
            .catch(() => {});
          const params = await readUrlParams(crawlPage);
          const leaked = LENS_PARAMS.filter((p) => params.has(p));
          if (leaked.length) {
            paramLeak.push(
              `leaving the ${lens} lens left ${leaked.join(", ")} in the URL, so the next ` +
                `link the reader copies carries state from a lens they are no longer in`,
            );
          }
        } catch (err) {
          rowDead.push(`${lens}: ${(err as Error).message.split("\n")[0]}`);
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description: `J4 exercised lens-scoped selection in: ${exercised.join(", ") || "none"}`,
      });
      reportFinding("journey.lens_row_dead", rowDead, {
        title: "lens rows that do not select what they name",
      });
      reportFinding("journey.lens_param_leak", paramLeak, {
        title: "lens-scoped URL params that survive leaving the lens",
      });
      const residue = await resetProbe(crawlPage, "J4 lens-scoped selection");
      reportFinding("journey.context_leak", residue, {
        title: "state that survived a journey's reset",
      });
      expect(rowDead, "lens rows that do not select what they name").toEqual([]);
      expect(paramLeak, "lens-scoped URL params that survive leaving the lens").toEqual([]);
      expect(residue, "state that survived J4's reset").toEqual([]);
    },
  );

  test(
    "J5: opening and closing an overlay mid-journey moves nothing",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      // The same claim surfaces.spec makes from the top level, made from
      // somewhere the reader has actually navigated to. A drop that only
      // happens when there is something to drop is the version that ships.
      const chain = pathToDeepest(contract);
      const parent = chain.length >= 2 ? chain[chain.length - 2] : null;
      const child = chain[chain.length - 1];
      test.skip(!parent, "the projection is one level deep; there is no context to hold");

      await navigateState(crawlPage, { drill: parent!.id, component: child.id });
      await expect
        .poll(async () => (await readNavState(crawlPage)).drill, { timeout: 30_000 , intervals: [100] })
        .toBe(parent!.id)
        .catch(() => {});

      const before = navFields(await readNavState(crawlPage));
      const moved: string[] = [];
      const opened: string[] = [];

      const overlays: { testId: string; root: string }[] = [
        { testId: "search-button", root: "search-overlay" },
        { testId: "findings-entry", root: "findings-surface" },
        { testId: "supply-chain-entry", root: "supply-chain-surface" },
        { testId: "tours-entry", root: "tours-list-overlay" },
        { testId: "help-button", root: "help-overlay" },
      ];

      for (const overlay of overlays) {
        const trigger = await visibleEntry(crawlPage, overlay.testId);
        if (!trigger) continue;
        try {
          await trigger.click({ timeout: 5_000  });
          await expect(
            crawlPage.locator(`[data-testid="${overlay.root}"]`).first(),
          ).toBeVisible({ timeout: 10_000  });
          opened.push(overlay.testId);
          await crawlPage.keyboard.press("Escape");
          await expect(crawlPage.locator(`[data-testid="${overlay.root}"]`)).toHaveCount(0, {
            timeout: 10_000,
          });

          const after = navFields(await readNavState(crawlPage));
          for (const [field, value] of Object.entries(after)) {
            if (before[field] !== value) {
              moved.push(
                `${overlay.testId}: ${field} went from "${before[field]}" to "${value}" ` +
                  `across an open and close`,
              );
            }
          }
        } catch (err) {
          // Same discipline as J4: a click that never becomes possible is
          // reported with what was sitting on it and what the app left the
          // page, so the finding names a cause rather than a timeout.
          const obstruction = await describeObstruction(
            crawlPage,
            `[data-testid="${overlay.testId}"]`,
          ).catch(() => "the obstruction could not be measured");
          moved.push(
            `${overlay.testId}: ${(err as Error).message.split("\n")[0]}: ${obstruction}; ` +
              `${await describeViewport(crawlPage)}`,
          );
          await navigateState(crawlPage, { drill: parent!.id, component: child.id }).catch(() => {});
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description:
          `J5 opened and closed ${opened.length} overlay(s) while drilled into ${parent!.id} ` +
          `with ${child.id} selected: ${opened.join(", ") || "none"}`,
      });
      reportFinding("journey.overlay_changed_nav", moved, {
        title: "overlays that move the reader when opened or closed",
      });
      const residue = await resetProbe(crawlPage, "J5 overlay hygiene");
      reportFinding("journey.context_leak", residue, {
        title: "state that survived a journey's reset",
      });
      expect(moved, "overlays that move the reader when opened or closed").toEqual([]);
      expect(residue, "state that survived J5's reset").toEqual([]);
    },
  );

  test(
    "J6: a deep link survives a cold reload unchanged",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      // A pasted link that reads differently the second time it is opened is a
      // link nobody can share, and the drift is always small enough to look
      // like nothing: one param dropped, one tab reset. Reading the beacon
      // twice around a reload is the cheapest way to see it.
      const chain = pathToDeepest(contract);
      const parent = chain.length >= 2 ? chain[chain.length - 2] : null;
      const child = chain[chain.length - 1];
      const nonDefaultLens = contract.lensesExpected.find((id) => id !== "structure");

      const link: Record<string, string | undefined> = {
        drill: parent?.id,
        component: child.id,
        tab: "overview",
      };
      // A lens rides only when the data warrants one, and only when it does not
      // own its own selection: entering the flow lens with a component param
      // would be testing two things at once.
      if (nonDefaultLens && nonDefaultLens !== "flow") link.lens = nonDefaultLens;

      await gotoState(crawlPage, link);
      await expect
        .poll(async () => (await readNavState(crawlPage)).selected, { timeout: 30_000 , intervals: [100] })
        .toBe(child.id)
        .catch(() => {});
      const first = await readNavState(crawlPage);
      const firstUrl = new URL(crawlPage.url()).search;

      await crawlPage.reload({ timeout: 60_000  });
      await waitForBoot(crawlPage, 60_000);
      await expect
        .poll(async () => (await readNavState(crawlPage)).selected, { timeout: 30_000 , intervals: [100] })
        .toBe(first.selected)
        .catch(() => {});
      const second = await readNavState(crawlPage);
      const secondUrl = new URL(crawlPage.url()).search;

      const drift: string[] = [];
      const a = navFields(first);
      const b = navFields(second);
      for (const [field, value] of Object.entries(a)) {
        if (b[field] !== value) {
          drift.push(`${field} read "${value}" before the reload and "${b[field]}" after`);
        }
      }
      if (firstUrl !== secondUrl) {
        drift.push(`the URL read "${firstUrl}" before the reload and "${secondUrl}" after`);
      }

      test.info().annotations.push({
        type: "coverage",
        description: `J6 reloaded the deep link ?${firstUrl.replace(/^\?/, "")}`,
      });
      reportFinding("journey.reload_drift", drift, {
        title: "deep links that read differently after a reload",
      });
      const residue = await resetProbe(crawlPage, "J6 cold reload");
      reportFinding("journey.context_leak", residue, {
        title: "state that survived a journey's reset",
      });
      expect(drift, "deep links that read differently after a reload").toEqual([]);
      expect(residue, "state that survived J6's reset").toEqual([]);
    },
  );

  test(
    "the Escape shortcut the help dialog advertises does what it says",
    { tag: ["@desktop"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      // Added while building the reset probe, because the probe could not use
      // the gesture the design named. HelpSystem's own shortcut list contains
      //
      //   { keys: ["Esc"], description: "Close panels / search" }
      //
      // and Escape is handled nowhere that closes the detail panel: every
      // Escape listener in the app (SearchOverlay, FindingsSurface,
      // SupplyChainSurface, InventoryPanel, AdminDashboard, TourPlayer,
      // HelpSystem) is registered only while its own surface is open. So the
      // app tells the reader a key does something it does not do.
      //
      // Recorded as its own case rather than as residue from every journey,
      // because it is one gap with one fix, and reporting it six times under
      // six journey labels would be six symptoms and no cause.
      const target = [...contract.components.values()][0];
      test.skip(!target, "no component to open a panel for");

      await navigateState(crawlPage, { component: target.id });
      await expect(crawlPage.locator('[data-testid="detail-panel"]').first()).toBeVisible({
        timeout: 30_000,
      });

      await crawlPage.keyboard.press("Escape");
      // Bounded and Node-enforced. The panel disappearing late is still the
      // panel disappearing; only never is a finding.
      const closed = await expect
        .poll(async () => crawlPage.locator('[data-testid="detail-panel"]').count(), {
          timeout: 5_000,
        })
        .toBe(0)
        .then(() => true)
        .catch(() => false);

      const broken = closed
        ? []
        : [
            `Escape leaves the detail panel for ${target.id} open, while the help dialog's ` +
              `own shortcut list advertises Esc as "Close panels / search"`,
          ];

      test.info().annotations.push({
        type: "coverage",
        description: "the help dialog's Esc shortcut checked against a detail panel",
      });
      reportFinding("journey.advertised_shortcut_dead", broken, {
        title: "keyboard shortcuts the help dialog advertises that do nothing",
      });
      expect(
        broken,
        "a shortcut the product teaches the reader in its own help text must work, or the " +
          "help text must not teach it",
      ).toEqual([]);
    },
  );
});
