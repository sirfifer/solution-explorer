/**
 * Tours: does the guided walkthrough actually walk?
 *
 * The owner's second named defect: a guided tour whose diagram does not snap to
 * and highlight each stop. It is the worst place for that to happen, because a
 * tour is what somebody is shown when they are being convinced the tool works;
 * a step whose narration describes a component the diagram never moves to reads
 * as the product not knowing what it is talking about.
 *
 * Tours are few by nature (four on this subject), so there is no sampling: every
 * tour is played end to end. Skipped entirely, with a coverage annotation
 * saying so, when the projection carries none.
 *
 * ── What "the step's target is realised" means, and why ──
 *
 * For a COMPONENT-ID target, four things at once, because any one of them alone
 * can be true while the reader is still lost:
 *   the beacon's selection is the target        (the app agrees where it is)
 *   the node carries React Flow's selected class(the diagram agrees)
 *   the node is fully inside the canvas box     (the reader can see it)
 *   the beacon's drill is the target's parent   (the reader is at the right level)
 * The drill rule is not invented here: store.navigateToComponent drills to the
 * PARENT and selects the child, and leaves the drill empty for a top-level
 * component. navigateToTourTarget routes every component-id target through it.
 *
 * For a FILE-PATH target, the app deliberately does something different, and
 * this spec follows the app rather than the other way round. There is no file
 * view to land on: openFileDeepLink resolves the owning component, drills to it,
 * and marks the file inside its Files tab. That behaviour is a fix, not an
 * oversight (comprehension-study S7: landing elsewhere left "the file nowhere
 * in sight"), and this suite has already once reported 14 false failures by
 * asserting the opposite (see search.spec.ts). So a file target is realised
 * when the app lands on a view that NAMES the file: a file-detail carrying that
 * path, or a component detail panel whose Files tab shows it.
 *
 * The same correction applies to a step's evidence link, which routes through
 * exactly the same openFileDeepLink. See the evidence test below.
 */

import {
  test,
  requireContract,
  expect,
  reportFinding,
  reportDiscovery,
  gotoState,
  navigateState,
  readNavState,
  resetProbe,
  cssEscape,
  waitForInView,
  waitForUnoccluded,
} from "./fixtures";
import type { Contract, ExpectedTour } from "./contract";

/** How long a step's node has to come fully into view before it has not. */
const SNAP_BUDGET_MS = 2_000;

/** Open the tour list from its entry point, waiting Node-side for the overlay. */
async function openTourList(page: import("@playwright/test").Page): Promise<void> {
  await page.locator('[data-testid="tours-entry"]').first().click({ timeout: 5_000  });
  await expect(page.locator('[data-testid="tours-list-overlay"]').first()).toBeVisible({
    timeout: 15_000,
  });
}

/**
 * Whether the app has landed somewhere that names `filePath`.
 *
 * Both accepted landings are the product's own: a file view carrying the path,
 * or the owning component with the file marked in its Files tab.
 */
async function landedOnFile(
  page: import("@playwright/test").Page,
  filePath: string,
): Promise<boolean> {
  const fileDetail = page.locator('[data-testid="file-detail"]');
  if ((await fileDetail.count()) > 0) {
    const shown = await fileDetail.first().getAttribute("data-file-path");
    if (shown === filePath) return true;
  }
  const leaf = filePath.split("/").pop() ?? filePath;
  const panel = page.locator('[data-testid="detail-panel"]');
  if ((await panel.count()) === 0) return false;
  const files = page.locator('[data-testid="detail-tabpanel"][data-tab="files"]');
  if ((await files.count()) === 0) return false;
  const text = await files.first().innerText().catch(() => "");
  return text.includes(leaf);
}

/**
 * Check one step's target and return everything wrong with it.
 *
 * Returns rather than asserts, so a tour with a bad step is walked to the end
 * and the report says which steps, not just that one did.
 */
async function checkStepTarget(
  page: import("@playwright/test").Page,
  contract: Contract,
  tour: ExpectedTour,
  step: number,
): Promise<{ missed: string[]; notInView: string[]; drillWrong: string[]; occluded: string[] }> {
  const missed: string[] = [];
  const notInView: string[] = [];
  const drillWrong: string[] = [];
  const occluded: string[] = [];
  const target = tour.targets[step];
  const where = `${tour.id} step ${step + 1}/${tour.stepCount} (${target})`;

  const component = contract.components.get(target);
  if (!component) {
    // A file-path target. The app's contract is the owning component with the
    // file marked, not a file view; see this file's header.
    const ok = await expect
      .poll(() => landedOnFile(page, target), { timeout: 10_000 , intervals: [100] })
      .toBe(true)
      .then(() => true)
      .catch(() => false);
    if (!ok) {
      missed.push(`${where}: the target is a file path and nothing on screen names it`);
    }
    return { missed, notInView, drillWrong, occluded };
  }

  await expect
    .poll(async () => (await readNavState(page)).selected, { timeout: 10_000 , intervals: [100] })
    .toBe(target)
    .catch(() => {});
  const state = await readNavState(page);

  if (state.selected !== target) {
    missed.push(`${where}: the beacon's selection is "${state.selected}"`);
  }
  // A single root the graph promoted (its children ARE the top level) is not
  // a level of its own, so a step onto one of its children lands on the top
  // level with no drill (store.ts isPromotedRoot). Whether the child is then
  // actually on the canvas is the node check below, which still has to pass.
  const promotedRootParent =
    contract.rootIds.length === 1 && component.parentId === contract.rootIds[0];
  const expectedDrill = component.parentId ?? "";
  if (state.drill !== expectedDrill && !(promotedRootParent && state.drill === "")) {
    drillWrong.push(
      `${where}: the drill is "${state.drill}", expected "${expectedDrill || "(top level)"}" ` +
        `(navigateToComponent drills to the parent and selects the child)`,
    );
  }

  const nodeSelector = `.react-flow__node[data-id="${cssEscape(target)}"]`;
  const node = page.locator(nodeSelector);
  // Poll rather than read once. The beacon's selection lands before the canvas
  // has finished laying out, and ELK's pass is asynchronous, so a single read
  // here reports the intermediate frame as "the target was grouped away". The
  // claim is the design's: the diagram snaps to each stop, within the same
  // budget the in-view check uses. The same mistake is recorded in
  // search.spec.ts, which polls the product outcome for exactly this reason.
  await expect
    .poll(async () => node.count(), { timeout: SNAP_BUDGET_MS, intervals: [100] })
    .toBeGreaterThan(0)
    .catch(() => {});
  if ((await node.count()) === 0) {
    // Say what the level DOES show. "No node" on its own reads as a rendering
    // bug; "six hero nodes and one aggregate, and the target is in neither" is
    // the actual shape of the problem and points at the level's own budgeting
    // rather than at the tour.
    const rendered = await page
      .locator(".react-flow__node")
      .evaluateAll((els) => els.map((el) => el.getAttribute("data-id") ?? ""));
    const aggregates = await page
      .locator('[data-testid="aggregate-node"]')
      .evaluateAll((els) => els.map((el) => el.getAttribute("data-aggregate-id") ?? ""));
    missed.push(
      `${where}: the step selects the component but the canvas renders no node for it. ` +
        `This drill level shows ${rendered.length - aggregates.length} component node(s) and ` +
        `${aggregates.length} aggregate(s) [${aggregates.join(", ") || "none"}], so the target ` +
        `has been grouped away and the narration describes something the diagram never shows`,
    );
    return { missed, notInView, drillWrong, occluded };
  }
  const cls = (await node.first().getAttribute("class")) ?? "";
  if (!cls.split(/\s+/).includes("selected")) {
    missed.push(`${where}: the node is on the canvas but is not highlighted as selected`);
  }
  if (!(await waitForInView(page, nodeSelector, SNAP_BUDGET_MS))) {
    notInView.push(
      `${where}: the node never came fully inside the canvas within ${SNAP_BUDGET_MS}ms`,
    );
  }
  // Geometry is only half of "the reader can see the stop". The step panel is
  // the obvious cover on a phone, but a bottom sheet or the drill hint will do
  // it too, so the question is asked of the browser rather than of a list of
  // suspects. Polled rather than read once: the 400ms pan animation that
  // follows a selection legitimately covers the node while it is still
  // travelling, so a single read right after the in-view wait catches the
  // animation, not a defect.
  const result = await waitForUnoccluded(page, nodeSelector, SNAP_BUDGET_MS);
  if (result.occluded) {
    occluded.push(
      `${where}: the node's centre is still covered by ${result.lastCover} after ` +
        `${result.coveredForMs}ms`,
    );
  }
  return { missed, notInView, drillWrong, occluded };
}

/**
 * Open the step panel's narration and step list if they are collapsed.
 *
 * Below the sm breakpoint the panel is a docked strip and the narration, the
 * evidence link and the step list are one tap away on the header, so that tap
 * is part of the reader's flow and part of this walk. Asked of the panel's own
 * data-expanded rather than of the viewport: a spec that branched on which
 * project it was would be testing the layout rather than the behaviour.
 */
async function ensureTourPanelExpanded(page: import("@playwright/test").Page): Promise<void> {
  const panel = page.locator('[data-testid="tour-step-panel"]').first();
  if ((await panel.count()) === 0) return;
  if ((await panel.getAttribute("data-expanded")) === "true") return;
  await page.locator('[data-testid="tour-panel-toggle"]').first().click({ timeout: 5_000 }).catch(() => {});
  await expect
    .poll(async () => panel.getAttribute("data-expanded"), { timeout: 5_000, intervals: [100] })
    .toBe("true")
    .catch(() => {});
}

// A timeout IS the finding in this spec, so the wait for one is short. Fifteen
// seconds to learn something knowable in five is minutes of nothing happening
// across a run with a dozen such findings, and every wait here stays
// Node-enforced either way. The exhaustive sweeps keep the generous default.
test.use({ actionTimeout: 5_000 });

test.describe("tours", () => {
  test(
    "the entry and the list agree with the manifest's tours",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      test.skip(contract.tours.length === 0, "this projection carries no tours");
      await navigateState(crawlPage, {});

      const entryWrong: string[] = [];
      const listWrong: string[] = [];

      const entry = crawlPage.locator('[data-testid="tours-entry"]');
      if ((await entry.count()) === 0) {
        entryWrong.push(
          `the projection carries ${contract.tours.length} tour(s) and no tours entry is offered`,
        );
      } else {
        const text = await entry.first().innerText();
        if (!text.includes(String(contract.tours.length))) {
          entryWrong.push(
            `the tours entry reads "${text.replace(/\s+/g, " ").trim()}" and never names the ` +
              `${contract.tours.length} tour(s) the projection carries`,
          );
        }
        await openTourList(crawlPage);

        const rows = await crawlPage
          .locator('[data-testid="tour-list-item"]')
          .evaluateAll((els) =>
            els.map((el) => ({
              id: el.getAttribute("data-tour-id") ?? "",
              steps: el.getAttribute("data-step-count") ?? "",
              stale: el.getAttribute("data-stale") ?? "",
            })),
          );

        // Authored order (I11): the list is never re-sorted, so this compares
        // the sequence, not the set. A reordered list is a real defect because
        // a tour is a narrative and its neighbours are part of the story.
        const shownIds = rows.map((r) => r.id);
        const expectedIds = contract.tours.map((t) => t.id);
        if (shownIds.join("|") !== expectedIds.join("|")) {
          listWrong.push(
            `the list shows [${shownIds.join(", ")}] but the manifest authors ` +
              `[${expectedIds.join(", ")}]`,
          );
        }
        for (const tour of contract.tours) {
          const row = rows.find((r) => r.id === tour.id);
          if (!row) continue;
          if (row.steps !== String(tour.stepCount)) {
            listWrong.push(
              `${tour.id} is listed with ${row.steps} steps; the manifest holds ${tour.stepCount}`,
            );
          }
          if ((row.stale === "true") !== tour.stale) {
            listWrong.push(
              `${tour.id} is marked stale=${row.stale} but its provenance says ${tour.stale}`,
            );
          }
        }
        await crawlPage.keyboard.press("Escape");
      }

      test.info().annotations.push({
        type: "coverage",
        description: `${contract.tours.length} tour(s) compared against the manifest`,
      });
      reportDiscovery("tours", contract.tours.map((t) => ({
        id: t.id,
        steps: t.stepCount,
        stale: t.stale,
      })));
      reportFinding("tour.entry_count", entryWrong, {
        title: "a tours entry that does not name the tours the projection holds",
      });
      reportFinding("tour.list_mismatch", listWrong, {
        title: "a tour list that disagrees with the manifest",
      });
      expect(entryWrong, "a tours entry that does not name what the projection holds").toEqual([]);
      expect(listWrong, "a tour list that disagrees with the manifest").toEqual([]);
    },
  );

  test(
    "every tour plays end to end, snapping to and highlighting each stop",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, contract, recorder }) => {
      await requireContract(crawlPage);
      test.skip(contract.tours.length === 0, "this projection carries no tours");
      // Every tour, every step, plus evidence and a jump per tour. Bounded by
      // the number of tours, which is small by nature, but generous enough that
      // a slow canvas reports rather than times the suite out.
      test.setTimeout(30 * 60 * 1000);

      const missed: string[] = [];
      const notInView: string[] = [];
      const drillWrong: string[] = [];
      const progressWrong: string[] = [];
      const evidenceDead: string[] = [];
      const jumpDead: string[] = [];
      const exitLeak: string[] = [];
      const occluded: string[] = [];
      const noisy: string[] = [];
      let stepsPlayed = 0;

      for (const [index, tour] of contract.tours.entries()) {
        try {
          recorder.reset();
          await navigateState(crawlPage, {});
          await openTourList(crawlPage);
          const row = crawlPage.locator(
            `[data-testid="tour-list-item"][data-tour-id="${cssEscape(tour.id)}"]`,
          );
          if ((await row.count()) === 0) {
            missed.push(`${tour.id}: not in the tour list, so it cannot be played`);
            continue;
          }
          await row.first().click({ timeout: 5_000  });

          const panel = crawlPage.locator('[data-testid="tour-step-panel"]');
          await expect(panel.first()).toBeVisible({ timeout: 15_000  });
          const panelTourId = await panel.first().getAttribute("data-tour-id");
          if (panelTourId !== tour.id) {
            missed.push(`${tour.id}: the step panel opened for "${panelTourId}"`);
            continue;
          }

          // Walk forward. The progress text is the reader's "where am I", and
          // it is asserted at every step because it is the only thing on screen
          // that says how much is left.
          for (let step = 0; step < tour.stepCount; step++) {
            if (step > 0) {
              const next = crawlPage.locator('[data-testid="tour-next"]');
              await next.first().click({ timeout: 5_000  });
              await expect
                .poll(
                  async () =>
                    (await crawlPage
                      .locator('[data-testid="tour-step-panel"]')
                      .first()
                      .getAttribute("data-step")) ?? "",
                  { timeout: 15_000 , intervals: [100] },
                )
                .toBe(String(step))
                .catch(() => {});
            }
            stepsPlayed++;

            const progress = (
              await crawlPage.locator('[data-testid="tour-progress"]').first().innerText()
            ).trim();
            const expectedProgress = `Step ${step + 1} of ${tour.stepCount}`;
            if (progress !== expectedProgress) {
              progressWrong.push(
                `${tour.id} step ${step + 1}: the panel reads "${progress}", expected ` +
                  `"${expectedProgress}"`,
              );
            }
            const beaconStep = (await readNavState(crawlPage)).tourStep;
            if (beaconStep !== String(step)) {
              progressWrong.push(
                `${tour.id} step ${step + 1}: the beacon's tour step reads "${beaconStep}"`,
              );
            }

            const result = await checkStepTarget(crawlPage, contract, tour, step);
            missed.push(...result.missed);
            notInView.push(...result.notInView);
            drillWrong.push(...result.drillWrong);
            occluded.push(...result.occluded);

            const problems = recorder.problems();
            if (problems.length) {
              noisy.push(`${tour.id} step ${step + 1}: ${problems[0]}`);
              recorder.reset();
            }
          }

          // Evidence, on one step per tour that carries it. The link routes
          // through openFileDeepLink, so the landing is the owning component
          // with the file marked, NOT a file view; see this file's header.
          const evidenceStep = tour.evidence.findIndex((f) => f !== null);
          if (evidenceStep >= 0) {
            await ensureTourPanelExpanded(crawlPage);
            await crawlPage
              .locator(`[data-testid="tour-step-item"][data-step="${evidenceStep}"]`)
              .first()
              .click({ timeout: 5_000  });
            const link = crawlPage.locator('[data-testid="tour-evidence-link"]');
            if ((await link.count()) === 0) {
              evidenceDead.push(
                `${tour.id} step ${evidenceStep + 1}: the manifest anchors it to ` +
                  `${tour.evidence[evidenceStep]} and the panel offers no evidence link`,
              );
            } else {
              await link.first().click({ timeout: 5_000  });
              const file = tour.evidence[evidenceStep] as string;
              const landed = await expect
                .poll(() => landedOnFile(crawlPage, file), { timeout: 15_000 , intervals: [100] })
                .toBe(true)
                .then(() => true)
                .catch(() => false);
              if (!landed) {
                // Say where it DID land. The step's own promise is "show me the
                // code" (TOURS_QUESTIONS: "Each step's evidence link opens the
                // exact file and line the step is anchored to"), so the useful
                // report is which surface the reader is looking at instead.
                const onComponent = await crawlPage
                  .locator('[data-testid="detail-panel"]')
                  .first()
                  .getAttribute("data-component-id")
                  .catch(() => null);
                const onTab = await crawlPage
                  .locator('[data-testid="detail-tab"][data-active="true"]')
                  .first()
                  .getAttribute("data-tab")
                  .catch(() => null);
                evidenceDead.push(
                  `${tour.id} step ${evidenceStep + 1}: the evidence link for ${file} left the ` +
                    `reader on ${onComponent ?? "no component"}'s "${onTab ?? "no"}" tab, which ` +
                    `never names the file`,
                );
              }
              // Following evidence must not end the walk: the reader is looking
              // at the code the step is about, and has to be able to carry on.
              const stillPanel = crawlPage.locator('[data-testid="tour-step-panel"]');
              if ((await stillPanel.count()) === 0) {
                evidenceDead.push(
                  `${tour.id} step ${evidenceStep + 1}: following evidence closed the tour`,
                );
              } else if (
                (await stillPanel.first().getAttribute("data-step")) !== String(evidenceStep)
              ) {
                evidenceDead.push(
                  `${tour.id} step ${evidenceStep + 1}: following evidence moved the walk to ` +
                    `step ${await stillPanel.first().getAttribute("data-step")}`,
                );
              }
            }
          }

          // Previous, from wherever the walk is now, back to the first step one
          // step at a time. A Previous that jumps or sticks is the same defect
          // as a Next that does.
          const panelStepNow = Number(
            (await crawlPage
              .locator('[data-testid="tour-step-panel"]')
              .first()
              .getAttribute("data-step")) ?? "0",
          );
          for (let step = panelStepNow; step > 0; step--) {
            await crawlPage.locator('[data-testid="tour-prev"]').first().click({ timeout: 5_000  });
            await expect
              .poll(
                async () =>
                  (await crawlPage
                    .locator('[data-testid="tour-step-panel"]')
                    .first()
                    .getAttribute("data-step")) ?? "",
                { timeout: 15_000 , intervals: [100] },
              )
              .toBe(String(step - 1))
              .catch(() => {});
            const at = await crawlPage
              .locator('[data-testid="tour-step-panel"]')
              .first()
              .getAttribute("data-step");
            if (at !== String(step - 1)) {
              progressWrong.push(
                `${tour.id}: Previous from step ${step + 1} landed on step ` +
                  `${Number(at) + 1}, not ${step}`,
              );
              break;
            }
          }

          // Jump: the middle step from the panel's own list.
          const middle = Math.floor(tour.stepCount / 2);
          if (tour.stepCount > 2) {
            await ensureTourPanelExpanded(crawlPage);
            const item = crawlPage.locator(
              `[data-testid="tour-step-item"][data-step="${middle}"]`,
            );
            if ((await item.count()) === 0) {
              jumpDead.push(`${tour.id}: the step panel lists no jump target for step ${middle + 1}`);
            } else {
              await item.first().click({ timeout: 5_000  });
              await expect
                .poll(
                  async () =>
                    (await crawlPage
                      .locator('[data-testid="tour-step-panel"]')
                      .first()
                      .getAttribute("data-step")) ?? "",
                  { timeout: 15_000 , intervals: [100] },
                )
                .toBe(String(middle))
                .catch(() => {});
              const at = await crawlPage
                .locator('[data-testid="tour-step-panel"]')
                .first()
                .getAttribute("data-step");
              if (at !== String(middle)) {
                jumpDead.push(
                  `${tour.id}: jumping to step ${middle + 1} left the panel on step ` +
                    `${Number(at) + 1}`,
                );
              } else {
                const result = await checkStepTarget(crawlPage, contract, tour, middle);
                missed.push(...result.missed.map((m) => `after a jump: ${m}`));
                notInView.push(...result.notInView.map((m) => `after a jump: ${m}`));
                occluded.push(...result.occluded.map((m) => `after a jump: ${m}`));
              }
            }
          }

          // Exit. The first tour exits with Escape, the rest with the button,
          // so both routes are exercised without playing every tour twice.
          if (index === 0) {
            await crawlPage.keyboard.press("Escape");
          } else {
            await crawlPage.locator('[data-testid="tour-exit"]').first().click({ timeout: 5_000  });
          }
          await expect(crawlPage.locator('[data-testid="tour-step-panel"]')).toHaveCount(0, {
            timeout: 10_000,
          });
          const exited = await readNavState(crawlPage);
          if (exited.tour !== "") {
            exitLeak.push(`${tour.id}: the beacon still names the tour after exiting`);
          }
          // The store documents that exiting LEAVES THE LAST SELECTION in place
          // ("clears the walk; leaves the last selection in place"), so a
          // selection here is correct behaviour and is not reported. What must
          // not survive is the walk itself.
          if (exited.tourStep !== "") {
            exitLeak.push(`${tour.id}: the beacon still carries tour step "${exited.tourStep}"`);
          }

          const residue = await resetProbe(crawlPage, `tour ${tour.id}`);
          exitLeak.push(...residue);
        } catch (err) {
          missed.push(`${tour.id}: ${(err as Error).message.split("\n")[0]}`);
          await navigateState(crawlPage, {}).catch(() => {});
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description:
          `${contract.tours.length} tour(s) played end to end, ${stepsPlayed} step(s) realised ` +
          `(no sampling: tours are few by nature)`,
      });

      reportFinding("tour.step_target_missed", missed, {
        title: "tour steps whose target is not selected and highlighted",
      });
      reportFinding("tour.step_not_in_view", notInView, {
        title: "tour steps whose node never comes into view",
      });
      reportFinding("tour.step_drill_wrong", drillWrong, {
        title: "tour steps that leave the reader at the wrong level",
      });
      reportFinding("tour.progress_wrong", progressWrong, {
        title: "tour progress that does not say where the reader is",
      });
      reportFinding("tour.evidence_dead", evidenceDead, {
        title: "evidence links that do not show the code the step is anchored to",
      });
      reportFinding("tour.jump_dead", jumpDead, {
        title: "step jumps that do not move the walk",
      });
      reportFinding("tour.exit_leak", exitLeak, {
        title: "state a tour leaves behind after it is exited",
      });
      reportFinding("graph.node_occluded", occluded, {
        title: "tour stops whose node is on the canvas and covered by something else",
      });
      reportFinding("tour.noisy", noisy, {
        title: "tour steps that logged a console error or a failed request",
        severity: "warn",
      });

      expect(missed, "tour steps whose target is not selected and highlighted").toEqual([]);
      expect(
        notInView,
        "tour steps whose node never comes into view, which is the diagram not snapping to " +
          "the stop the narration is describing",
      ).toEqual([]);
      expect(drillWrong, "tour steps that leave the reader at the wrong level").toEqual([]);
      expect(progressWrong, "tour progress that does not say where the reader is").toEqual([]);
      expect(evidenceDead, "evidence links that do not show the code").toEqual([]);
      expect(jumpDead, "step jumps that do not move the walk").toEqual([]);
      expect(exitLeak, "state a tour leaves behind after it is exited").toEqual([]);
      expect(
        occluded,
        "tour stops the reader cannot see because something is painted over the node",
      ).toEqual([]);
      expect(noisy, "tour steps that logged an error or a 404").toEqual([]);
    },
  );
});
