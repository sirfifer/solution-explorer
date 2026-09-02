/**
 * Surfaces: is exactly what the data warrants on screen, and does it work?
 *
 * Reachability walks the tree; this walks the perimeter. The viewer's globally
 * reachable features (coverage, gaps, findings, supply chain, tours, search,
 * help, the lens switcher) each appear only when the projection carries the
 * data behind them, which is the right design and is also exactly why nobody
 * notices when one stops appearing: an absent entry point looks identical to a
 * dataset that never had one.
 *
 * So presence is checked in BOTH directions against the predicate table in
 * contract.ts. An entry the data warrants and the DOM lacks is a feature the
 * reader cannot get to. An entry the DOM shows that the data does not warrant
 * is worse: the reader clicks it believing something is behind it.
 *
 * Then one level of use. Trusting presence and never opening anything would let
 * a surface that renders an empty box pass forever, and a blank surface and a
 * broken one look identical (the Files tab lesson in this directory's README).
 *
 * ── Two places where this spec deliberately does NOT follow one uniform rule ──
 *
 * COVERAGE AND GAPS ARE DISCLOSURES, NOT OVERLAYS. Both are inline expanders
 * inside their own banner: the badge toggles `coverage-panel`, the gaps banner
 * toggles its list, and neither registers an Escape handler because neither is
 * modal. Asserting "press Escape and it closes" against them would be asserting
 * a promise the product never made, which is how this suite previously produced
 * three false public bug reports. They are re-collapsed by clicking their own
 * toggle again, and they are expected to leave the beacon's overlay list empty
 * because they are not overlays.
 *
 * THE LENS SWITCHER IS A CONTROL. `lens-select` is a `<select>`; it has no
 * surface to open, no root to find and nothing to close. Its correctness is
 * the whole of the second test below, so the use test skips it by name rather
 * than by silently finding nothing.
 *
 * ── The detail-tab rules, and which of them this spec asserts ──
 *
 * Read from DetailPanel.tsx, which is the single source of truth for tab
 * presence, and settled against the manifest (see readTabFacts in contract.ts
 * for why the manifest and not the detail shard):
 *
 *   overview       always
 *   docs           hasDocsTabContent(docs): readme, claude_md,
 *                  architecture_notes, api_docs, changelog, or key_decisions.
 *                  Deliberately NOT patterns/tech_stack/api_endpoints/env_vars,
 *                  which the Overview tab and the node hover show instead; the
 *                  predicate exists so the tab never appears only to say it is
 *                  empty (GUI run finding V3.1).
 *   ai             component.ai_enhance
 *   testing        component.testing with test_files > 0 or a named framework
 *   actions        component.actions non-empty
 *   capabilities   component.capabilities non-empty
 *   data           component.data_entities non-empty, OR the component appears
 *                  as an accessor_id in entity_access
 *   files/symbols/relationships  always (counts may be zero)
 *   status         component.live_status with at least one status
 *
 * `status` is the one rule the data cannot settle: a static projection never
 * carries live_status and a live deployment adds it at runtime, so this spec
 * asserts nothing about that tab in either direction. Everything else above is
 * asserted both ways.
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
  navFields,
  visibleEntry,
  ensureDetailPanel,
} from "./fixtures";
import {
  componentBudget,
  sampleComponents,
  loadParams,
  isDeclaredOff,
  entryToken,
} from "./contract";

/** A surface with no text at all is blank; the honest-empty rule needs words. */
const MIN_PANEL_TEXT = 3;

/** How many components to check tab presence on. Bounded by design. */
const TAB_SAMPLE = 12;

type EntryKind = "overlay" | "disclosure" | "control";

interface EntryUse {
  /** The overlay name the beacon must list while it is open, or null. */
  overlay: string | null;
  /** The surface root that must appear. */
  root: string;
  kind: EntryKind;
}

/**
 * What opening each entry is supposed to produce. Keyed by the entry's own
 * test id, so the table here and the predicate table in contract.ts line up
 * without either one repeating the other's job.
 */
const ENTRY_USE: Record<string, EntryUse> = {
  "tours-entry": { overlay: "tours", root: "tours-list-overlay", kind: "overlay" },
  "findings-entry": { overlay: "findings", root: "findings-surface", kind: "overlay" },
  "supply-chain-entry": {
    overlay: "supply-chain",
    root: "supply-chain-surface",
    kind: "overlay",
  },
  "search-button": { overlay: "search", root: "search-overlay", kind: "overlay" },
  "help-button": { overlay: "help", root: "help-overlay", kind: "overlay" },
  "coverage-badge": { overlay: null, root: "coverage-panel", kind: "disclosure" },
  "gaps-banner": { overlay: null, root: "gaps-entry", kind: "disclosure" },
  // The trust ledger is where coverage and producer gaps now live. Unlike the
  // two bands it replaced it IS modal: it opens a drawer and closes on Escape.
  "trust-ledger-entry": { overlay: "trust", root: "trust-drawer", kind: "overlay" },
  "lens-select": { overlay: null, root: "lens-select", kind: "control" },
};

// A timeout IS the finding in this spec, so the wait for one is short. Fifteen
// seconds to learn something knowable in five is minutes of nothing happening
// across a run with a dozen such findings, and every wait here stays
// Node-enforced either way. The exhaustive sweeps keep the generous default.
test.use({ actionTimeout: 5_000 });

test.describe("surfaces", () => {
  test(
    "every entry point the data warrants is present, and no others",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      await navigateState(crawlPage, {});

      const params = loadParams();
      const missing: string[] = [];
      const unwarranted: string[] = [];
      const declaredOffPresent: string[] = [];
      const declaredOffAbsent: string[] = [];
      for (const entry of contract.entryPoints) {
        // Any of the row's ids satisfies it. An affordance is allowed to move
        // house, and several did when the opening band was retired; what is not
        // allowed is for the reader to lose the way in. See ExpectedEntry.
        let count = 0;
        for (const testId of entry.testIds) {
          count += await crawlPage.locator(`[data-testid="${testId}"]`).count();
        }
        const names = entry.testIds.join(" or ");
        const token = entryToken(entry.testIds);
        if (isDeclaredOff(params, token)) {
          // The claim inverts: absence is expected, presence is the finding,
          // because the build is then not the build the parameters describe.
          if (count > 0) {
            declaredOffPresent.push(`${names} is present although ${token} is declared off`);
          } else {
            declaredOffAbsent.push(token);
          }
          continue;
        }
        if (entry.expected && count === 0) {
          missing.push(`${names} is absent although ${entry.because}`);
        }
        if (!entry.expected && count > 0) {
          unwarranted.push(`${names} is present although ${entry.because}`);
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description:
          `${contract.entryPoints.length} entry point predicates evaluated; ` +
          `expected present: ${contract.entryPoints
            .filter((e) => e.expected)
            .map((e) => e.testIds.join("|"))
            .join(", ") || "none"}` +
          (declaredOffAbsent.length
            ? `; declared off by params: ${declaredOffAbsent.join(", ")}`
            : ""),
      });

      reportDiscovery("entry_points", {
        present: await Promise.all(
          contract.entryPoints.map(async (e) => ({
            ids: e.testIds,
            expected: e.expected,
            declared_off: isDeclaredOff(params, entryToken(e.testIds)),
            present: (
              await Promise.all(
                e.testIds.map((id) => crawlPage.locator(`[data-testid="${id}"]`).count()),
              )
            ).reduce((a, b) => a + b, 0) > 0,
          })),
        ),
        declared_off: [...params.declaredOff],
        notes: params.notes,
      });
      reportFinding("surface.declared_off_present", declaredOffPresent, {
        title: "features the parameters declare off that this build still offers",
      });
      reportFinding("surface.missing", missing, {
        title: "entry points the data warrants that the UI never offers",
      });
      reportFinding("surface.unwarranted", unwarranted, {
        title: "entry points the UI offers that the data does not warrant",
      });
      expect(missing, "entry points the data warrants that the UI never offers").toEqual([]);
      expect(
        unwarranted,
        "entry points the UI offers with no data behind them, so the reader clicks " +
          "believing there is something there",
      ).toEqual([]);
      expect(
        declaredOffPresent,
        "features the parameters declare off and this build still offers, so the build is " +
          "not the one the parameters describe",
      ).toEqual([]);
    },
  );

  test(
    "the lens switcher offers exactly the lenses the data warrants",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      await navigateState(crawlPage, {});
      const select = crawlPage.locator('[data-testid="lens-select"]');

      const offered =
        (await select.count()) === 0
          ? []
          : await select
              .first()
              .locator("option")
              .evaluateAll((els) => els.map((el) => (el as HTMLOptionElement).value));

      const params = loadParams();
      const declaredOff = contract.lensesExpected.filter((id) =>
        isDeclaredOff(params, `lens:${id}`),
      );
      const expected = contract.lensesExpected.filter(
        (id) => !isDeclaredOff(params, `lens:${id}`),
      );
      const missing = expected.filter((id) => !offered.includes(id));
      const unwarranted = offered.filter(
        (id) => !expected.includes(id) && !isDeclaredOff(params, `lens:${id}`),
      );
      const declaredOffPresent = offered
        .filter((id) => isDeclaredOff(params, `lens:${id}`))
        .map((id) => `the ${id} lens is offered although lens:${id} is declared off`);

      test.info().annotations.push({
        type: "coverage",
        description:
          `lenses expected [${expected.join(", ")}]; offered [${offered.join(", ") || "none"}]` +
          (declaredOff.length
            ? `; declared off by params: ${declaredOff.map((id) => `lens:${id}`).join(", ")}`
            : ""),
      });

      reportDiscovery("lenses", {
        offered,
        expected,
        declared_off: declaredOff.map((id) => `lens:${id}`),
      });
      reportFinding("surface.declared_off_present", declaredOffPresent, {
        title: "lenses the parameters declare off that this build still offers",
      });
      reportFinding("surface.lens_missing", missing, {
        title: "lenses the data warrants that the switcher does not offer",
      });
      reportFinding("surface.lens_unwarranted", unwarranted, {
        title: "lenses the switcher offers that the data does not warrant",
      });
      expect(missing, "lenses the data warrants that the switcher does not offer").toEqual([]);
      expect(
        unwarranted,
        "lenses the switcher offers with no data behind them",
      ).toEqual([]);
      expect(
        declaredOffPresent,
        "lenses the parameters declare off and the switcher still offers",
      ).toEqual([]);
      expect(
        declaredOffPresent,
        "lenses the parameters declare off and the switcher still offers",
      ).toEqual([]);
    },
  );

  test(
    "every present entry opens a surface with something in it, closes, and changes nothing",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, contract, recorder }) => {
      await requireContract(crawlPage);
      await navigateState(crawlPage, {});

      const dead: string[] = [];
      const blank: string[] = [];
      const wontClose: string[] = [];
      const changedNav: string[] = [];
      const noisy: string[] = [];
      const exercised: string[] = [];

      for (const entry of contract.entryPoints) {
        // Whichever of the row's ids is actually on screen is the one to drive.
        const testId = (
          await Promise.all(
            entry.testIds.map(async (id) =>
              (await crawlPage.locator(`[data-testid="${id}"]`).count()) > 0 ? id : null,
            ),
          )
        ).find((id): id is string => id !== null);
        if (!testId) continue; // absence is the first test's finding
        if (exercised.includes(testId)) continue; // two rows can resolve to one home
        const use = ENTRY_USE[testId];
        if (!use || use.kind === "control") continue;

        // The one on screen, opening the overflow menu if that is where this
        // viewport keeps it.
        const trigger = await visibleEntry(crawlPage, testId);
        if (!trigger) {
          dead.push(`${testId} is in the DOM but cannot be reached on this viewport`);
          continue;
        }

        // Each entry inside its own try. A crawl is a survey: one entry that
        // throws must not abandon the rest, and a case that dies partway
        // reports no findings at all because findings are recorded at the end.
        try {
          recorder.reset();
          const before = navFields(await readNavState(crawlPage));

          await trigger.click({ timeout: 5_000  });

          const root = crawlPage.locator(`[data-testid="${use.root}"]`);
          try {
            await expect(root.first()).toBeVisible({ timeout: 10_000  });
          } catch {
            dead.push(`${testId} does not open ${use.root}`);
            continue;
          }
          exercised.push(testId);

          const text = (await root.first().innerText().catch(() => "")).trim();
          if (text.length < MIN_PANEL_TEXT) {
            blank.push(`${testId} opens ${use.root} but it renders no text at all`);
          }

          // The beacon must agree that this overlay is open. A surface on
          // screen that the app's own account of itself does not mention is the
          // drift this beacon exists to make impossible to miss.
          const opened = await readNavState(crawlPage);
          if (use.overlay && !opened.overlays.includes(use.overlay)) {
            changedNav.push(
              `${testId} opened ${use.root} but the beacon's overlays read ` +
                `"${opened.overlays.join(",")}" and never name ${use.overlay}`,
            );
          }
          if (!use.overlay && opened.overlays.length > 0) {
            changedNav.push(
              `${testId} is an inline disclosure but opened overlays ` +
                `"${opened.overlays.join(",")}"`,
            );
          }

          // Closing. An overlay closes with Escape, because it is modal and
          // says so. A disclosure closes by clicking its own toggle again: it
          // is not modal, registers no Escape handler, and never claimed to.
          if (use.kind === "overlay") {
            await crawlPage.keyboard.press("Escape");
          } else {
            await trigger.click({ timeout: 5_000  });
          }

          try {
            await expect(crawlPage.locator(`[data-testid="${use.root}"]`)).toHaveCount(0, {
              timeout: 10_000,
            });
          } catch {
            wontClose.push(
              `${testId}: ${use.root} is still on screen after ` +
                `${use.kind === "overlay" ? "Escape" : "a second click on the entry"}`,
            );
            // Leave the page somewhere inert so the next entry gets a fair try.
            await navigateState(crawlPage, {});
            continue;
          }

          const closed = await readNavState(crawlPage);
          if (closed.overlays.length > 0) {
            wontClose.push(
              `${testId}: the beacon still lists overlays "${closed.overlays.join(",")}" ` +
                `after closing`,
            );
          }

          // Opening and closing a surface must not move the reader. This is the
          // owner's named defect class seen from the smallest possible
          // distance: if a glance at the findings list silently drops your
          // selection, every longer journey is already broken.
          const after = navFields(closed);
          for (const [field, value] of Object.entries(after)) {
            if (before[field] !== value) {
              changedNav.push(
                `${testId}: ${field} went from "${before[field]}" to "${value}" ` +
                  `across an open/close that should have changed nothing`,
              );
            }
          }

          const problems = recorder.problems();
          if (problems.length) noisy.push(`${testId}: ${problems[0]}`);
        } catch (err) {
          dead.push(`${testId}: ${(err as Error).message.split("\n")[0]}`);
          await navigateState(crawlPage, {}).catch(() => {});
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description: `${exercised.length} entry point(s) opened and closed: ${
          exercised.join(", ") || "none"
        }`,
      });

      reportFinding("surface.dead_entry", dead, {
        title: "entry points that do not open the surface they promise",
      });
      reportFinding("surface.blank_surface", blank, {
        title: "surfaces that open empty rather than saying they are empty",
      });
      reportFinding("surface.wont_close", wontClose, {
        title: "surfaces that will not close the way they say they do",
      });
      reportFinding("surface.open_changed_nav", changedNav, {
        title: "surfaces whose opening or closing moved the reader",
      });
      reportFinding("surface.noisy", noisy, {
        title: "surfaces that logged a console error or a failed request",
        severity: "warn",
      });

      expect(dead, "entry points that do not open the surface they promise").toEqual([]);
      expect(blank, "surfaces that open with nothing in them").toEqual([]);
      expect(wontClose, "surfaces that will not close").toEqual([]);
      expect(changedNav, "surfaces whose opening or closing moved the reader").toEqual([]);
      expect(noisy, "surfaces that logged an error or a 404").toEqual([]);
    },
  );

  test(
    "each component offers exactly the detail tabs the data warrants",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage, contract }) => {
      await requireContract(crawlPage);
      // Depth-stratified so deep components are not the ones dropped: depth is
      // where the tab rules have actually gone wrong before.
      const budget = Math.min(componentBudget() || TAB_SAMPLE, TAB_SAMPLE);
      const { chosen } = sampleComponents(contract, budget);

      const tabMissing: string[] = [];
      const tabUnwarranted: string[] = [];
      let checked = 0;

      for (const comp of chosen) {
        try {
          await navigateState(crawlPage, { component: comp.id });
          // On a phone the panel is inside a bottom sheet that starts collapsed.
          await ensureDetailPanel(crawlPage);
          const panel = crawlPage.locator('[data-testid="detail-panel"]');
          try {
            await expect(panel.first()).toHaveAttribute("data-component-id", comp.id, {
              timeout: 20_000,
            });
          } catch {
            continue; // unreachable components are reachability.spec's finding
          }
          const facts = contract.tabFacts.get(comp.id);
          if (!facts) continue;

          const onScreen = new Set(
            (
              await crawlPage
                .locator('[data-testid="detail-tab"]')
                .evaluateAll((els) => els.map((el) => el.getAttribute("data-tab") ?? ""))
            ).filter(Boolean),
          );
          checked++;

          for (const [tab, warranted] of Object.entries(facts)) {
            if (warranted && !onScreen.has(tab)) {
              tabMissing.push(`${comp.id}: the data warrants a ${tab} tab and none is offered`);
            }
            if (!warranted && onScreen.has(tab)) {
              tabUnwarranted.push(
                `${comp.id}: a ${tab} tab is offered although the data warrants none`,
              );
            }
          }
        } catch (err) {
          tabMissing.push(`${comp.id}: ${(err as Error).message.split("\n")[0]}`);
        }
      }

      test.info().annotations.push({
        type: "coverage",
        description:
          `${checked}/${contract.components.size} components checked for tab presence ` +
          `(ai, docs, testing, actions, capabilities, data; status is not settled by the data)`,
      });
      reportDiscovery("tab_sample", { checked, of: contract.components.size, budget });

      reportFinding("surface.tab_missing", tabMissing, {
        title: "tabs the data warrants that the component does not offer",
      });
      reportFinding("surface.tab_unwarranted", tabUnwarranted, {
        title: "tabs offered with no data behind them",
      });
      expect(
        tabMissing.slice(0, 25),
        "tabs the data warrants that the component does not offer",
      ).toEqual([]);
      expect(
        tabUnwarranted.slice(0, 25),
        "tabs offered with no data behind them, which the reader opens to find nothing",
      ).toEqual([]);
    },
  );
});
