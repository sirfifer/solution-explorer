/**
 * The Overview front door, and the transition between the two apertures.
 *
 * The viewer now has two apertures over one projection: Overview, where a fresh
 * reader lands, and the workbench, which is everything the other specs test.
 * The front-door work specifies the transition between them as LOSSLESS:
 * subject, question, lens, semantic level, selected object and tour step are
 * route state and survive the switch in both directions.
 *
 * That claim is exactly this suite's class of defect. A handoff that quietly
 * drops the level, or a return that forgets the drill, is invisible on either
 * screen alone: both look correct, and only the pair is wrong. It is also the
 * highest-stakes place for it to happen, because the handoff is the first thing
 * a new reader ever does with the product.
 *
 * Everything here reads the beacon AND the visible expression of the same
 * state, as the rest of the suite does, and every case is gated on the contract
 * being present so an older build reports "limited" rather than a wall of red.
 *
 * ── Two things this spec deliberately does not assume ──
 *
 * THE SIDECAR MAY BE ABSENT. Overview reads `architecture/orientation.json`,
 * and when it is missing the app builds a fallback from the architecture
 * (`buildOrientationFallback`) rather than failing. Route availability can then
 * only be checked against a document nobody authored, so O3 says so in a
 * coverage annotation and checks the shape it can still check.
 *
 * ONE ROUTE, MANY TARGET KINDS. A question route's target names a lens, a
 * surface, or a tour, and `openTarget` in SystemOverview.tsx applies whichever
 * fields are present. So O4 asserts per target kind rather than asserting one
 * shape and calling the others broken.
 */

import {
  test,
  requireContract,
  expect,
  reportFinding,
  reportDiscovery,
  gotoState,
  readNavState,
  readUrlParams,
  navFields,
  cssEscape,
  waitForInView,
  describeObstruction,
  visibleEntry,
} from "./fixtures";
import { loadOrientation, type ExpectedOrientation } from "./contract";

/** A surface with no text at all is blank; the honest-empty rule needs words. */
const MIN_PANEL_TEXT = 3;

/** The three opening postures the Overview offers. */
const DIRECTIONS = ["portrait", "questions", "atlas"] as const;

/** Land on the front door with storage cleared, as a first-time reader does. */
async function gotoOverview(page: import("@playwright/test").Page): Promise<void> {
  await gotoState(page, { mode: "overview" });
  await expect(page.locator('[data-testid="system-overview"]').first()).toBeVisible({
    timeout: 30_000,
  });
}

/** Return to the front door through the control the product offers. */
async function returnToOverview(
  page: import("@playwright/test").Page,
): Promise<string | null> {
  // Close what the handoff opened, first.
  //
  // A route whose target is a SURFACE hands off with that surface on top of the
  // workbench, and the return control is then behind a full-screen modal. A
  // reader closes the thing they opened before pressing the thing behind it; a
  // test that clicked straight through would report its own impatience as a
  // dead control.
  //
  // Waited on the DOM, not on the beacon: what blocks the click is a mounted
  // dialog root, and the beacon can report the store's flag cleared a frame
  // before React unmounts the element. One Escape per open surface, bounded,
  // because that is what the product asks of a reader too.
  const dialogRoots =
    '[data-testid="findings-surface"], [data-testid="supply-chain-surface"], ' +
    '[data-testid="tours-list-overlay"], [data-testid="search-overlay"], ' +
    '[data-testid="trust-drawer"], [data-testid="preferences-drawer"], ' +
    '[data-testid="help-overlay"], [data-testid="orientation-walk"]';
  for (let attempt = 0; attempt < 3; attempt++) {
    if ((await page.locator(dialogRoots).count()) === 0) break;
    await page.keyboard.press("Escape").catch(() => {});
    await expect
      .poll(async () => page.locator(dialogRoots).count(), { timeout: 3_000, intervals: [100] })
      .toBe(0)
      .catch(() => {});
  }
  if ((await page.locator(dialogRoots).count()) > 0) {
    return "a surface the handoff opened will not close, so the return control stays covered";
  }

  const back = page.locator('[data-testid="open-overview"]');
  if ((await back.count()) === 0) return "the workbench offers no return-to-Overview control";
  try {
    await back.first().click({ timeout: 5_000 });
  } catch (err) {
    // Say what was in the way rather than that a click timed out.
    const obstruction = await describeObstruction(page, '[data-testid="open-overview"]').catch(
      () => "the obstruction could not be measured",
    );
    return `the return control would not accept a click: ${obstruction}`;
  }
  await expect
    .poll(async () => (await readNavState(page)).mode, { timeout: 15_000 , intervals: [100] })
    .toBe("overview")
    .catch(() => {});
  const state = await readNavState(page);
  return state.mode === "overview"
    ? null
    : `the return control was clicked and the beacon still reads mode="${state.mode}" ` +
        `(overlays "${state.overlays.join(",")}")`;
}

// A timeout IS the finding in this spec, so the wait for one is short. Fifteen
// seconds to learn something knowable in five is minutes of nothing happening
// across a run with a dozen such findings, and every wait here stays
// Node-enforced either way. The exhaustive sweeps keep the generous default.
test.use({ actionTimeout: 5_000 });

test.describe("overview", () => {
  test(
    "O1: a bare URL lands on the front door, not the workbench",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, recorder }) => {
      await requireContract(crawlPage);
      // Deliberately NOT through gotoState's default: this case is about what a
      // reader gets when they name nothing at all, which is the one navigation
      // in the suite that must not carry mode.
      await crawlPage.goto("/");
      await crawlPage.waitForSelector('[data-testid="nav-state"]', {
        state: "attached",
        timeout: 60_000,
      });

      const wrong: string[] = [];
      await expect
        .poll(async () => (await readNavState(crawlPage)).mode, { timeout: 30_000 , intervals: [100] })
        .toBe("overview")
        .catch(() => {});
      const state = await readNavState(crawlPage);

      if (state.mode !== "overview") {
        wrong.push(`a bare URL booted into the "${state.mode}" aperture, not Overview`);
      }
      if ((await crawlPage.locator('[data-testid="system-overview"]').count()) === 0) {
        wrong.push("a bare URL rendered no system-overview root");
      }
      // The workbench's own furniture must not be on screen: two apertures
      // rendering at once is the failure mode a mode flag makes easy.
      if ((await crawlPage.locator('[data-testid="tree-navigator"]').count()) > 0) {
        wrong.push("the Overview rendered the workbench's tree navigator as well");
      }
      if ((await crawlPage.locator(".react-flow").count()) > 0) {
        wrong.push("the Overview rendered the workbench's graph canvas as well");
      }

      test.info().annotations.push({
        type: "coverage",
        description: `O1 booted a bare URL into mode="${state.mode}"`,
      });
      reportFinding("overview.boot_wrong_mode", wrong, {
        title: "a fresh origin that does not land on the front door",
      });
      expect(wrong, "a fresh origin must land on the Overview front door").toEqual([]);
      expect(recorder.problems(), "booting the front door must be clean").toEqual([]);
    },
  );

  test(
    "O2: every opening direction renders something",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, recorder }) => {
      await requireContract(crawlPage);
      await gotoOverview(crawlPage);

      const blank: string[] = [];
      const exercised: string[] = [];

      for (const direction of DIRECTIONS) {
        try {
          recorder.reset();
          const button = crawlPage.locator(
            `[data-testid="overview-direction"][data-direction="${direction}"]`,
          );
          if ((await button.count()) === 0) {
            blank.push(`the ${direction} direction is not offered at all`);
            continue;
          }
          await button.first().click({ timeout: 5_000  });
          await expect
            .poll(async () => (await readNavState(crawlPage)).direction, { timeout: 10_000 , intervals: [100] })
            .toBe(direction)
            .catch(() => {});

          const state = await readNavState(crawlPage);
          if (state.direction !== direction) {
            blank.push(
              `clicking the ${direction} direction left the beacon reading "${state.direction}"`,
            );
            continue;
          }
          // The visible half: the root publishes the same direction, and the
          // section under it says something.
          const root = crawlPage.locator('[data-testid="system-overview"]').first();
          if ((await root.getAttribute("data-direction")) !== direction) {
            blank.push(`the ${direction} direction is in the store but not on the Overview root`);
          }
          const text = (await crawlPage.locator("main").first().innerText().catch(() => "")).trim();
          if (text.length < MIN_PANEL_TEXT) {
            blank.push(`the ${direction} direction renders no text at all`);
          }
          const problems = recorder.problems();
          if (problems.length) blank.push(`${direction}: ${problems[0]}`);
          exercised.push(direction);
        } catch (err) {
          blank.push(`${direction}: ${(err as Error).message.split("\n")[0]}`);
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description: `O2 exercised ${exercised.length}/3 directions: ${exercised.join(", ")}`,
      });
      reportFinding("overview.direction_blank", blank, {
        title: "opening directions that render nothing",
      });
      expect(blank, "opening directions that render nothing").toEqual([]);
    },
  );

  test(
    "O3: the question routes on screen are the ones the sidecar authored",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, request }) => {
      await requireContract(crawlPage);
      const orientation = await loadOrientation(request);
      await gotoOverview(crawlPage);
      await crawlPage
        .locator('[data-testid="overview-direction"][data-direction="questions"]')
        .first()
        .click({ timeout: 5_000  });

      const shown = await crawlPage
        .locator('[data-testid="question-route"]')
        .evaluateAll((els) =>
          els.map((el) => ({
            id: el.getAttribute("data-route-id") ?? "",
            available: el.getAttribute("data-available") === "true",
          })),
        );

      if (!orientation) {
        // The app builds a fallback orientation when the sidecar is absent, so
        // the Overview still works; what cannot be checked is whether a route's
        // availability matches something a person authored, because nobody did.
        test.info().annotations.push({
          type: "coverage",
          description:
            `O3: no architecture/orientation.json, so the Overview is running the generated ` +
            `fallback and route availability cannot be checked against data; ` +
            `${shown.length} route(s) rendered`,
        });
        expect(shown.length, "the Overview offers at least one question route").toBeGreaterThan(0);
        return;
      }

      const expected = orientation.questionRoutes;
      const missing = expected
        .filter((r) => !shown.some((s) => s.id === r.id))
        .map((r) => `${r.id} is authored in the sidecar and not offered`);
      const unwarranted = shown
        .filter((s) => !expected.some((r) => r.id === s.id))
        .map((s) => `${s.id} is offered and the sidecar does not author it`);
      const availability = expected
        .filter((r) => shown.some((s) => s.id === r.id && s.available !== r.available))
        .map(
          (r) =>
            `${r.id} reads available=${!r.available} on screen and ${r.available} in the sidecar`,
        );

      test.info().annotations.push({
        type: "coverage",
        description:
          `O3 compared ${shown.length} rendered route(s) against ${expected.length} authored; ` +
          `${expected.filter((r) => r.available).length} authored available`,
      });
      reportDiscovery("question_routes", {
        rendered: shown,
        authored: expected.map((r) => ({ id: r.id, available: r.available })),
      });
      reportFinding("overview.route_missing", [...missing, ...unwarranted], {
        title: "question routes that disagree with the orientation sidecar",
      });
      reportFinding("overview.route_availability", availability, {
        title: "question routes whose availability disagrees with the sidecar",
      });
      expect(missing, "question routes the sidecar authors that are not offered").toEqual([]);
      expect(unwarranted, "question routes offered that the sidecar does not author").toEqual([]);
      expect(
        availability,
        "routes whose availability on screen contradicts the sidecar, so a reader is either " +
          "offered a dead end or denied a live one",
      ).toEqual([]);
    },
  );

  test(
    "O4: every available route hands off to what it names",
    { tag: ["@desktop"] },
    async ({ crawlPage, request }) => {
      await requireContract(crawlPage);
      test.setTimeout(20 * 60 * 1000);
      const orientation = await loadOrientation(request);

      const dead: string[] = [];
      const wrongTarget: string[] = [];
      const exercised: string[] = [];

      await gotoOverview(crawlPage);
      await crawlPage
        .locator('[data-testid="overview-direction"][data-direction="questions"]')
        .first()
        .click({ timeout: 5_000  });

      const routes = await crawlPage
        .locator('[data-testid="question-route"]')
        .evaluateAll((els) =>
          els.map((el) => ({
            id: el.getAttribute("data-route-id") ?? "",
            available: el.getAttribute("data-available") === "true",
          })),
        );

      for (const route of routes) {
        const target = orientation?.questionRoutes.find((r) => r.id === route.id)?.target ?? null;
        try {
          await gotoOverview(crawlPage);
          await crawlPage
            .locator('[data-testid="overview-direction"][data-direction="questions"]')
            .first()
            .click({ timeout: 5_000  });

          const row = crawlPage.locator(
            `[data-testid="question-route"][data-route-id="${cssEscape(route.id)}"]`,
          );

          if (!route.available) {
            // An unavailable route is disabled, and clicking a disabled button
            // must do nothing at all. Forced past the disabled state on
            // purpose: the claim is that the app ignores it, not that
            // Playwright refuses to try.
            const before = await readNavState(crawlPage);
            await row.first().click({ timeout: 5_000, force: true }).catch(() => {});
            const after = await readNavState(crawlPage);
            if (after.mode !== before.mode) {
              wrongTarget.push(
                `unavailable route ${route.id} still handed off to the ${after.mode} aperture`,
              );
            }
            continue;
          }

          // Choosing the question, then continuing with it: two gestures,
          // because the panel answers first and hands off second.
          await row.first().click({ timeout: 5_000  });
          const go = crawlPage.locator(
            `[data-testid="question-route-continue"][data-route-id="${cssEscape(route.id)}"]`,
          );
          if ((await go.count()) === 0) {
            dead.push(`route ${route.id} offers no way to continue with the question`);
            continue;
          }
          await go.first().click({ timeout: 5_000  });

          await expect
            .poll(async () => (await readNavState(crawlPage)).mode, { timeout: 20_000 , intervals: [100] })
            .toBe("workbench")
            .catch(() => {});
          const landed = await readNavState(crawlPage);
          if (landed.mode !== "workbench") {
            dead.push(`route ${route.id} did not hand off to the workbench`);
            continue;
          }
          exercised.push(route.id);

          // Per target kind, because a route names whichever of the three it
          // has and openTarget applies exactly those.
          if (target?.lens) {
            if (landed.lens !== target.lens) {
              wrongTarget.push(
                `route ${route.id} names the ${target.lens} lens and landed on "${landed.lens}"`,
              );
            } else if (
              // Structure is the default, and buildUrl deliberately omits it:
              // "Only emit the lens param when it is non-default, so Structure
              // URLs (and old links) stay clean and unchanged (P6-1)." Asserting
              // it would be asserting against the product's own decision.
              target.lens !== "structure" &&
              (await readUrlParams(crawlPage)).get("lens") !== target.lens
            ) {
              wrongTarget.push(`route ${route.id} entered the ${target.lens} lens without the URL`);
            }
            if (target.semantic_level && landed.level !== target.semantic_level) {
              wrongTarget.push(
                `route ${route.id} names level ${target.semantic_level} and landed on ` +
                  `"${landed.level}"`,
              );
            }
          }
          if (target?.surface === "findings") {
            const visible =
              (await crawlPage.locator('[data-testid="findings-surface"]').count()) > 0;
            if (!visible || !landed.overlays.includes("findings")) {
              wrongTarget.push(
                `route ${route.id} names the findings surface; visible=${visible}, ` +
                  `overlays="${landed.overlays.join(",")}"`,
              );
            }
          }
          if (target?.tour_id) {
            const panel = crawlPage.locator('[data-testid="tour-step-panel"]');
            const onTour = (await panel.count()) > 0
              ? await panel.first().getAttribute("data-tour-id")
              : null;
            if (onTour !== target.tour_id) {
              wrongTarget.push(
                `route ${route.id} names tour ${target.tour_id} and the step panel shows ` +
                  `"${onTour ?? "no tour"}"`,
              );
            }
          }

          const returnProblem = await returnToOverview(crawlPage);
          if (returnProblem) {
            dead.push(`route ${route.id}: ${returnProblem}`);
          }
        } catch (err) {
          dead.push(`route ${route.id}: ${(err as Error).message.split("\n")[0]}`);
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description:
          `O4 handed off ${exercised.length}/${routes.length} route(s): ` +
          `${exercised.join(", ") || "none"}` +
          (orientation ? "" : "; no sidecar, so target kinds could not be checked"),
      });
      reportFinding("overview.route_dead", dead, {
        title: "question routes that do not hand off at all",
      });
      reportFinding("overview.route_wrong_target", wrongTarget, {
        title: "question routes that hand off somewhere other than what they name",
      });
      expect(dead, "question routes that do not hand off at all").toEqual([]);
      expect(wrongTarget, "question routes that land somewhere other than what they name").toEqual(
        [],
      );
    },
  );

  test(
    "O5: every portrait card opens the component it names",
    { tag: ["@desktop"] },
    async ({ crawlPage }) => {
      await requireContract(crawlPage);
      test.setTimeout(20 * 60 * 1000);

      await gotoOverview(crawlPage);
      await crawlPage
        .locator('[data-testid="overview-direction"][data-direction="portrait"]')
        .first()
        .click({ timeout: 5_000  });

      const cards = await crawlPage
        .locator('[data-testid="portrait-card"]')
        .evaluateAll((els) =>
          els.map((el) => ({
            id: el.getAttribute("data-node-id") ?? "",
            target: el.getAttribute("data-target") ?? "",
          })),
        );
      test.skip(cards.length === 0, "the portrait offers no area cards");

      const dead: string[] = [];
      let opened = 0;

      for (const card of cards) {
        try {
          await gotoOverview(crawlPage);
          await crawlPage
            .locator('[data-testid="overview-direction"][data-direction="portrait"]')
            .first()
            .click({ timeout: 5_000  });
          const button = crawlPage.locator(
            `[data-testid="portrait-card"][data-node-id="${cssEscape(card.id)}"]`,
          );
          if ((await button.count()) === 0) continue;

          if (!card.target) {
            dead.push(`portrait area "${card.id}" names no component to open`);
            continue;
          }
          await button.first().click({ timeout: 5_000  });

          await expect
            .poll(async () => (await readNavState(crawlPage)).selected, { timeout: 20_000 , intervals: [100] })
            .toBe(card.target)
            .catch(() => {});
          const landed = await readNavState(crawlPage);
          if (landed.mode !== "workbench") {
            dead.push(`portrait area "${card.id}" did not hand off to the workbench`);
            continue;
          }
          if (landed.selected !== card.target) {
            dead.push(
              `portrait area "${card.id}" names ${card.target} and selected "${landed.selected}"`,
            );
            continue;
          }
          opened++;

          // The same in-view rule the graph spec uses: a selection the reader
          // cannot see is not a landing.
          const nodeSelector = `.react-flow__node[data-id="${cssEscape(card.target)}"]`;
          await expect
            .poll(async () => crawlPage.locator(nodeSelector).count(), {
              timeout: 20_000,
              intervals: [100],
            })
            .toBeGreaterThan(0)
            .catch(() => {});
          if ((await crawlPage.locator(nodeSelector).count()) === 0) {
            dead.push(
              `portrait area "${card.id}" selected ${card.target} and the canvas renders no ` +
                `node for it`,
            );
          } else if (!(await waitForInView(crawlPage, nodeSelector, 2_000))) {
            dead.push(
              `portrait area "${card.id}" selected ${card.target} and its node never came fully ` +
                `into view`,
            );
          }

          await returnToOverview(crawlPage);
        } catch (err) {
          dead.push(`portrait area "${card.id}": ${(err as Error).message.split("\n")[0]}`);
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description: `O5 opened ${opened}/${cards.length} portrait area card(s)`,
      });
      reportDiscovery("portrait_cards", cards);
      reportFinding("overview.card_dead", dead, {
        title: "portrait cards that do not open the component they name",
      });
      expect(dead, "portrait cards that do not open the component they name").toEqual([]);
    },
  );

  test(
    "O6: the round trip between apertures loses nothing",
    { tag: ["@desktop"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      // The lossless claim, stated by the front-door design and checkable only
      // as a pair: each screen looks right on its own and only the round trip
      // is wrong.
      const nested = [...contract.components.values()].find((c) => c.parentId !== null);
      test.skip(!nested, "the projection is one level deep; there is no drill to preserve");
      const nonDefaultLens = contract.lensesExpected.find(
        (id) => id !== "structure" && id !== "flow",
      );

      await gotoState(crawlPage, {
        drill: nested!.parentId ?? undefined,
        component: nested!.id,
        lens: nonDefaultLens,
        level: "domain",
      });
      await expect
        .poll(async () => (await readNavState(crawlPage)).selected, { timeout: 30_000 , intervals: [100] })
        .toBe(nested!.id)
        .catch(() => {});

      const before = navFields(await readNavState(crawlPage));
      const lost: string[] = [];
      const backWrong: string[] = [];

      await returnToOverview(crawlPage);
      const atOverview = await readNavState(crawlPage);
      if (atOverview.mode !== "overview") {
        lost.push(`the return control left the reader in the "${atOverview.mode}" aperture`);
      }
      if ((await crawlPage.locator('[data-testid="system-overview"]').count()) === 0) {
        lost.push("the return control changed the mode without rendering the Overview");
      }

      const forward = crawlPage.locator('[data-testid="open-workbench"]');
      if ((await forward.count()) === 0) {
        lost.push("the Overview offers no way back into the workbench");
      } else {
        await forward.first().click({ timeout: 5_000  });
        await expect
          .poll(async () => (await readNavState(crawlPage)).mode, { timeout: 20_000 , intervals: [100] })
          .toBe("workbench")
          .catch(() => {});
        const after = navFields(await readNavState(crawlPage));
        for (const field of ["drill", "selected", "lens", "level"]) {
          if (after[field] !== before[field]) {
            lost.push(
              `${field} was "${before[field]}" before the round trip and "${after[field]}" after`,
            );
          }
        }
      }

      // Browser back after a handoff returns to the front door, and forward
      // re-applies the workbench. The mode rides in the URL, so history is the
      // only honest way to check it.
      await gotoOverview(crawlPage);
      const card = crawlPage.locator('[data-testid="open-workbench"]');
      if ((await card.count()) > 0) {
        // Measured from history.length, not from where back happens to land.
        // Depending on the landing would make this case a hostage to whatever
        // navigation preceded it: if the handoff writes no history entry at
        // all, "back" goes to some earlier page and the failure reads as if the
        // wrong aperture was restored, when the real fact is that no entry was
        // ever created. The length is the mechanism, and it is unambiguous.
        const historyBefore = await crawlPage.evaluate(() => window.history.length);
        await card.first().click({ timeout: 5_000  });
        await expect
          .poll(async () => (await readNavState(crawlPage)).mode, { timeout: 20_000 , intervals: [100] })
          .toBe("workbench")
          .catch(() => {});
        const handedOff = navFields(await readNavState(crawlPage));
        const historyAfter = await crawlPage.evaluate(() => window.history.length);
        if (historyAfter === historyBefore) {
          backWrong.push(
            `the handoff into the workbench wrote no history entry (history.length stayed at ` +
              `${historyBefore}), so browser back cannot return to the front door`,
          );
        }

        await crawlPage.goBack({ timeout: 30_000  }).catch(() => {});
        await expect
          .poll(async () => (await readNavState(crawlPage)).mode, { timeout: 20_000 , intervals: [100] })
          .toBe("overview")
          .catch(() => {});
        const wentBack = await readNavState(crawlPage);
        if (historyAfter > historyBefore && wentBack.mode !== "overview") {
          backWrong.push(
            `browser back after a handoff left the reader in the "${wentBack.mode}" aperture`,
          );
        }

        await crawlPage.goForward({ timeout: 30_000  }).catch(() => {});
        await expect
          .poll(async () => (await readNavState(crawlPage)).mode, { timeout: 20_000 , intervals: [100] })
          .toBe("workbench")
          .catch(() => {});
        const wentForward = navFields(await readNavState(crawlPage));
        const forwardFields =
          historyAfter > historyBefore ? ["drill", "selected", "lens", "level"] : [];
        for (const field of forwardFields) {
          if (wentForward[field] !== handedOff[field]) {
            backWrong.push(
              `forward restored ${field}="${wentForward[field]}", expected ` +
                `"${handedOff[field]}"`,
            );
          }
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description:
          `O6 round-tripped drill=${before.drill} selected=${before.selected} ` +
          `lens=${before.lens} level=${before.level}`,
      });
      reportFinding("overview.roundtrip_lost_state", lost, {
        title: "state lost crossing between the two apertures",
      });
      reportFinding("overview.back_wrong_mode", backWrong, {
        title: "browser history that does not restore the aperture it left",
      });
      expect(
        lost,
        "the transition between apertures is specified as lossless, so anything the reader " +
          "had before it must still be there after",
      ).toEqual([]);
      expect(backWrong, "browser history that does not restore the aperture").toEqual([]);
    },
  );

  test(
    "O7: trust and preferences open, close, and are honoured",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage }) => {
      await requireContract(crawlPage);
      await gotoOverview(crawlPage);

      const broken: string[] = [];
      const drawers: { trigger: string; root: string; overlay: string }[] = [
        { trigger: "trust-ledger-entry", root: "trust-drawer", overlay: "trust" },
      ];

      for (const drawer of drawers) {
        const trigger = crawlPage.locator(`[data-testid="${drawer.trigger}"]`);
        if ((await trigger.count()) === 0) continue;
        try {
          const before = navFields(await readNavState(crawlPage));
          await trigger.first().click({ timeout: 5_000  });
          await expect(crawlPage.locator(`[data-testid="${drawer.root}"]`).first()).toBeVisible({
            timeout: 10_000,
          });
          const open = await readNavState(crawlPage);
          if (!open.overlays.includes(drawer.overlay)) {
            broken.push(
              `${drawer.root} is on screen and the beacon's overlays read ` +
                `"${open.overlays.join(",")}"`,
            );
          }
          await crawlPage.keyboard.press("Escape");
          await expect(crawlPage.locator(`[data-testid="${drawer.root}"]`)).toHaveCount(0, {
            timeout: 10_000,
          });
          const after = navFields(await readNavState(crawlPage));
          for (const [field, value] of Object.entries(after)) {
            if (before[field] !== value) {
              broken.push(
                `${drawer.root}: ${field} went from "${before[field]}" to "${value}" across an ` +
                  `open and close`,
              );
            }
          }
        } catch (err) {
          broken.push(`${drawer.root}: ${(err as Error).message.split("\n")[0]}`);
        }
      }

      // Preferences is reached from the Overview header's own control rather
      // than a testid of its own, so it is opened by the store's flag through
      // the same button the reader uses.
      const prefsButton = crawlPage.locator('button[aria-label="Viewer preferences"]');
      const notHonoured: string[] = [];
      if ((await prefsButton.count()) > 0) {
        try {
          await prefsButton.first().click({ timeout: 5_000  });
          await expect(
            crawlPage.locator('[data-testid="preferences-drawer"]').first(),
          ).toBeVisible({ timeout: 10_000  });
          const open = await readNavState(crawlPage);
          if (!open.overlays.includes("preferences")) {
            broken.push(
              `preferences-drawer is on screen and the beacon's overlays read ` +
                `"${open.overlays.join(",")}"`,
            );
          }

          // The start-view preference is the one that changes what a bare URL
          // does, which is the whole promise of the setting.
          const select = crawlPage
            .locator('[data-testid="preferences-drawer"] select')
            .first();
          await select.selectOption("workbench", { timeout: 10_000  });
          await crawlPage.keyboard.press("Escape");
          await crawlPage.goto("/");
          await crawlPage.waitForSelector('[data-testid="nav-state"]', {
            state: "attached",
            timeout: 60_000,
          });
          await expect
            .poll(async () => (await readNavState(crawlPage)).mode, { timeout: 20_000 , intervals: [100] })
            .toBe("workbench")
            .catch(() => {});
          let mode = (await readNavState(crawlPage)).mode;
          if (mode !== "workbench") {
            notHonoured.push(
              `start view was set to workbench and a bare URL still booted into "${mode}"`,
            );
          }

          // And back, so the run leaves the product on its own default.
          await crawlPage.goto("/?mode=overview");
          await crawlPage.waitForSelector('[data-testid="system-overview"]', {
            timeout: 60_000,
          });
          await crawlPage
            .locator('button[aria-label="Viewer preferences"]')
            .first()
            .click({ timeout: 5_000  });
          await crawlPage
            .locator('[data-testid="preferences-drawer"] select')
            .first()
            .selectOption("overview", { timeout: 10_000  });
          await crawlPage.keyboard.press("Escape");
          await crawlPage.goto("/");
          await crawlPage.waitForSelector('[data-testid="nav-state"]', {
            state: "attached",
            timeout: 60_000,
          });
          await expect
            .poll(async () => (await readNavState(crawlPage)).mode, { timeout: 20_000 , intervals: [100] })
            .toBe("overview")
            .catch(() => {});
          mode = (await readNavState(crawlPage)).mode;
          if (mode !== "overview") {
            notHonoured.push(
              `start view was set back to overview and a bare URL still booted into "${mode}"`,
            );
          }
        } catch (err) {
          broken.push(`preferences-drawer: ${(err as Error).message.split("\n")[0]}`);
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description: "O7 exercised the trust drawer and the start-view preference",
      });
      reportFinding("overview.drawer_broken", broken, {
        title: "front-door drawers that do not open, close, or hold still",
      });
      reportFinding("overview.preference_not_honoured", notHonoured, {
        title: "viewer preferences that do not change what the product does",
      });
      expect(broken, "front-door drawers that do not open, close, or hold still").toEqual([]);
      expect(
        notHonoured,
        "a preference the reader sets and the product ignores is worse than one it does not offer",
      ).toEqual([]);
    },
  );

  test(
    "O8: search from the front door lands in the workbench",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      await gotoOverview(crawlPage);

      const dead: string[] = [];
      const button = await visibleEntry(crawlPage, "search-button");
      test.skip(!button, "the Overview offers no reachable search button");

      await button!.click({ timeout: 5_000  });
      const input = crawlPage.locator('[data-testid="search-input"]');
      try {
        await expect(input.first()).toBeVisible({ timeout: 15_000  });
      } catch {
        dead.push("the Overview's search button does not open the search overlay");
      }

      if (dead.length === 0) {
        // A component whose name is its own, so the first component result is
        // unambiguous. Drawn from the projection, never typed in.
        const target = [...contract.components.values()]
          .filter((c) => c.name.length >= 4)
          .sort((a, b) => a.id.localeCompare(b.id))[0];
        if (target) {
          await input.first().fill(target.name, { timeout: 30_000  });
          const row = crawlPage.locator(
            '[data-testid="search-result"][data-result-kind="component"]',
          );
          try {
            await expect(row.first()).toBeVisible({ timeout: 15_000  });
            const landedOn = await row.first().getAttribute("data-result-id");
            await row.first().click({ timeout: 5_000  });

            await expect
              .poll(async () => (await readNavState(crawlPage)).mode, { timeout: 20_000 , intervals: [100] })
              .toBe("workbench")
              .catch(() => {});
            const state = await readNavState(crawlPage);
            if (state.mode !== "workbench") {
              dead.push(
                `choosing a component from Overview's search left the reader in the ` +
                  `"${state.mode}" aperture`,
              );
            }
            if (landedOn && state.selected !== landedOn) {
              dead.push(
                `Overview's search chose ${landedOn} and the workbench selected ` +
                  `"${state.selected}"`,
              );
            }
          } catch {
            dead.push(`searching "${target.name}" from the Overview returned no component row`);
          }
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description: "O8 searched from the front door and followed the first component result",
      });
      reportFinding("overview.search_dead", dead, {
        title: "search from the front door that does not land in the workbench",
      });
      expect(dead, "search from the front door that does not land in the workbench").toEqual([]);
    },
  );
  test(
    "O9: the front door says what the system is, with evidence",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, request }) => {
      await requireContract(crawlPage);
      const orientation = await loadOrientation(request);
      await gotoOverview(crawlPage);

      const identity = orientation?.identity ?? null;
      if (!identity || !identity.statement) {
        // The honest-empty case: a projection written before the identity pass
        // has nothing to say about what the subject is, and the Overview keeps
        // its older headline. There is no defect to find, only nothing to
        // check, and the rule says which.
        test.info().annotations.push({
          type: "coverage",
          description:
            "O9: identity absent in sidecar, so the front door is running its " +
            "pre-identity headline and the statement cannot be checked",
        });
        expect(
          await crawlPage.locator('[data-testid="system-overview"]').count(),
          "the Overview still renders without an identity block",
        ).toBeGreaterThan(0);
        return;
      }

      const wrong: string[] = [];
      const headline = crawlPage.locator('[data-testid="identity-statement"]');
      if ((await headline.count()) === 0) {
        wrong.push("the sidecar states what the system is and the page shows no statement");
      } else {
        // The page prints the summary, which is the statement without the
        // subject clause, because it shows the subject's name as its title.
        // An older sidecar carries only the statement.
        const shown = (await headline.first().innerText()).replace(/\s+/g, " ").trim();
        const authored = (identity.summary ?? identity.statement).replace(/\s+/g, " ").trim();
        if (shown !== authored) {
          wrong.push(
            `the headline reads "${shown}" and the sidecar authored "${authored}"`,
          );
        }
      }

      const chips = crawlPage.locator('[data-testid="form-factor"]');
      const chipCount = await chips.count();
      if (chipCount !== identity.formFactors.length) {
        wrong.push(
          `the sidecar records ${identity.formFactors.length} form factor(s) and the ` +
            `page offers ${chipCount} chip(s)`,
        );
      }

      // One chip is opened, because the promise is not that evidence exists in
      // a JSON file but that a reader can reach it.
      const first = identity.formFactors[0];
      const firstEvidence = first?.evidence[0]?.file;
      if (chipCount > 0 && firstEvidence) {
        await chips.first().click({ timeout: 5_000 });
        const panel = crawlPage.locator('[data-testid="form-factor-evidence"]');
        try {
          await expect(panel.first()).toBeVisible({ timeout: 10_000 });
          const text = await panel.first().innerText();
          if (!text.includes(firstEvidence)) {
            wrong.push(
              `opening the ${first.kind} chip did not show its evidence file ${firstEvidence}`,
            );
          }
        } catch {
          wrong.push(`the ${first.kind} chip does not reveal its evidence when clicked`);
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description:
          `O9 checked the statement and ${chipCount} form-factor chip(s) against the sidecar`,
      });
      reportDiscovery("identity", {
        statement: identity.statement,
        kinds: identity.formFactors.map((row) => row.kind),
      });
      reportFinding("overview.identity_unstated", wrong, {
        title: "a front door that does not say what the system is, with its evidence",
      });
      expect(
        wrong,
        "the front door must say what the system is and show the file that proves it",
      ).toEqual([]);
    },
  );

  test(
    "O10: counts stay out of the first viewport",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage }) => {
      await requireContract(crawlPage);
      await gotoOverview(crawlPage);
      await crawlPage
        .locator('[data-testid="overview-direction"][data-direction="portrait"]')
        .first()
        .click({ timeout: 5_000 });

      const wrong: string[] = [];
      const viewport = crawlPage.viewportSize();
      const tiles = crawlPage.locator('[data-se="stat"]');
      const tileCount = await tiles.count();
      for (let index = 0; index < tileCount; index++) {
        const box = await tiles.nth(index).boundingBox();
        if (!box || !viewport) continue;
        const inside = box.y < viewport.height && box.y + box.height > 0;
        if (inside) {
          const key = await tiles.nth(index).locator('[data-se="stat-key"]').innerText()
            .catch(() => "a count");
          wrong.push(`a "${key}" tile is in the first viewport of the Portrait posture`);
        }
      }

      // The counts are not deleted, only demoted: the trust route must still be
      // on the page, or the reader has lost the ledger instead of gaining a
      // front door.
      const summary = crawlPage.locator('[data-testid="scale-summary"]');
      const trustChip = crawlPage.locator('[data-testid="trust-ledger-entry"]');
      if ((await summary.count()) === 0 && (await trustChip.count()) === 0) {
        wrong.push("the Portrait posture offers no route to the counts at all");
      }

      test.info().annotations.push({
        type: "coverage",
        description:
          `O10 measured ${tileCount} count tile(s) at ` +
          `${viewport ? `${viewport.width}x${viewport.height}` : "an unknown viewport"}`,
      });
      reportFinding("overview.counts_lead", wrong, {
        title: "raw counts occupying the first thing a newcomer reads",
      });
      expect(wrong, "raw counts must not lead the front door").toEqual([]);
    },
  );

  test(
    "O10.1: a UI capture is real, provenance-labelled, and opens its source",
    { tag: ["@desktop"] },
    async ({ crawlPage, request, recorder }) => {
      await requireContract(crawlPage);
      const response = await request.get("/architecture/ui-surfaces.json");
      if (!response.ok()) {
        test.info().annotations.push({
          type: "coverage",
          description: "O10.1: no ui-surfaces.json is attached to this dataset; honest missing-capture rendering is covered by the component test",
        });
        return;
      }
      const surfaces = await response.json() as {
        screens: Array<{
          capture: { source_match: "exact" | "representative" };
          image: { width: number; height: number };
          hotspots: Array<{
            label: string;
            evidence: { component_id: string; file: string; line: number };
          }>;
        }>;
      };
      const authored = surfaces.screens[0];
      expect(authored, "the sidecar must author at least one screen").toBeTruthy();
      await gotoOverview(crawlPage);

      const preview = crawlPage.locator('[data-testid="interface-preview"]');
      await preview.scrollIntoViewIfNeeded();
      await expect(preview).toBeVisible();
      expect(await preview.getAttribute("data-source-match")).toBe(authored.capture.source_match);
      const provenance = (await preview.locator('[data-testid="capture-provenance"]').innerText()).toLowerCase();
      expect(provenance).toContain(authored.capture.source_match === "exact" ? "exact" : "representative");

      const image = preview.locator("img").first();
      await expect.poll(async () => image.evaluate((node: HTMLImageElement) => node.complete && node.naturalWidth > 0)).toBe(true);
      expect(await image.evaluate((node: HTMLImageElement) => [node.naturalWidth, node.naturalHeight])).toEqual([
        authored.image.width,
        authored.image.height,
      ]);
      const stageHotspots = preview.locator('[data-testid="interface-image-stage"] button');
      expect(await stageHotspots.count()).toBe(authored.hotspots.length);

      const first = authored.hotspots[0];
      recorder.reset();
      await stageHotspots.first().click();
      await expect.poll(async () => (await readNavState(crawlPage)).mode).toBe("workbench");
      await expect.poll(async () => (await readNavState(crawlPage)).selected).toBe(first.evidence.component_id);
      await expect(crawlPage.locator('[data-testid="detail-tab"][data-tab="files"][data-active="true"]')).toBeVisible();
      expect(recorder.problems(), "the screenshot-to-source handoff must be clean").toEqual([]);

      test.info().annotations.push({
        type: "coverage",
        description: `O10.1 loaded a ${authored.capture.source_match} ${authored.image.width}x${authored.image.height} capture with ${authored.hotspots.length} hotspot(s) and opened ${first.evidence.file}:${first.evidence.line}`,
      });
    },
  );

  test(
    "O11: SysCorpus frames every Overview direction without displacing the subject",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage }) => {
      await requireContract(crawlPage);
      await gotoOverview(crawlPage);

      const wrong: string[] = [];
      const subjectName = (await crawlPage.locator('[data-testid="overview-title"]').innerText()).trim();
      const brand = crawlPage.locator('[data-testid="syscorpus-brand"]');
      const context = crawlPage.locator('[data-testid="syscorpus-overview-context"]');
      const footer = crawlPage.locator('[data-testid="publication-footer"]');

      if (!(await context.isVisible())) {
        wrong.push("the first page does not visibly explain what this SysCorpus view contains");
      }
      if ((await brand.getAttribute("href")) !== "https://syscorpus.com/") {
        wrong.push("the primary SysCorpus mark does not link to syscorpus.com");
      }
      const contextText = (await context.innerText()).replace(/\s+/g, " ");
      if (!contextText.includes("SysCorpus") || !contextText.includes(subjectName)) {
        wrong.push(`the product frame does not identify both SysCorpus and ${subjectName}`);
      }
      if (!contextText.includes(`An explorable, evidence-linked model of ${subjectName}`)) {
        wrong.push("the first-page description reduces the subject to a generic map");
      }
      if ((await context.locator('[data-testid="overview-capability"]').count()) !== 3) {
        wrong.push("the first-page explanation is not broken into three scannable capabilities");
      }
      for (const phrase of ["Understand the system", "Trace it into the code", "Investigate from different angles"]) {
        if (!contextText.includes(phrase)) wrong.push(`the first-page explanation omits "${phrase}"`);
      }
      const interfaceGuide = context.locator('[data-testid="overview-interface-guide"]');
      if (!(await interfaceGuide.isVisible())) {
        wrong.push("the first page offers no visible route to the fuller interface guide");
      } else {
        await interfaceGuide.click();
        const help = crawlPage.locator('[data-testid="help-overlay"]');
        if (!(await help.isVisible()) || !(await help.innerText()).includes(`Meet ${subjectName} through the lens of SysCorpus`)) {
          wrong.push("the first-page interface link does not open the in-product Guide");
        }
        await crawlPage.getByRole("button", { name: "Close help" }).click();
      }
      const footerText = (await footer.innerText()).replace(/\s+/g, " ");
      if (!footerText.includes("SysCorpus") || !footerText.includes("© 2025-2026 Richard Amerman")) {
        wrong.push("the footer does not carry the SysCorpus identity and specific software copyright");
      }
      if ((await footer.locator('a[href="https://syscorpus.com/"]').count()) === 0) {
        wrong.push("the footer offers no link to the SysCorpus website");
      }

      for (const direction of ["portrait", "questions", "atlas"] as const) {
        await crawlPage.locator(`[data-testid="overview-direction"][data-direction="${direction}"]`).click();
        if ((await context.count()) === 0) wrong.push(`${direction} removes the SysCorpus product frame`);
        if ((await crawlPage.locator('[data-testid="overview-title"]').innerText()).trim() !== subjectName) {
          wrong.push(`${direction} displaces the project name from the header`);
        }
      }

      reportFinding("overview.product_unframed", wrong, {
        title: "an Overview direction that loses the product or subject identity",
      });
      expect(wrong, "SysCorpus and the viewed project must remain first-class together").toEqual([]);
    },
  );
});
