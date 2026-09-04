/**
 * Page fixtures for the crawl: a clean origin, and a recorder that makes a
 * console error or an undeclared 404 fail the case that caused it.
 *
 * The recorder matters more than it looks. A React app that throws inside a
 * panel renders an error boundary and keeps going, so a sweep that only asserts
 * "the title is right" passes over a component whose whole detail view blew up.
 * Every navigation therefore carries two assertions: the thing we asked for is
 * on screen, and nothing screamed while putting it there.
 */

import { test as base, expect, type Page, type ConsoleMessage } from "@playwright/test";
import { allowedErrorPaths, loadContract, type Contract } from "./contract";

const ORIENTATION_DISMISSED_KEY = "arch-viz-orientation-v1";

export interface Recorder {
  consoleErrors: string[];
  failedRequests: string[];
  reset(): void;
  /** Everything recorded since the last reset that is not on the allowlist. */
  problems(): string[];
}

function isAllowed(url: string, allowed: string[]): boolean {
  return allowed.some((fragment) => url.includes(fragment));
}

/**
 * The contract-presence gate.
 *
 * A build that predates the selector contract publishes no `nav-state`, and
 * every test that reads it then fails for one reason, forty times, drowning
 * whatever the run was actually meant to find. That is the same mistake as
 * picking the biggest component as the lens representative: one cause,
 * reported as forty findings, and the reader learns nothing.
 *
 * So the beacon is probed once per worker, on the first boot, and its absence
 * skips every test that needs it with a single annotation naming the cause. The
 * legacy specs that predate the beacon (reachability, depth, search) still run,
 * because they are exactly the ones an older build can still answer.
 *
 * The run is reported as LIMITED, never as green: the annotation rides into the
 * reporter's coverage lines, so a board showing "passed" also shows why that
 * word is worth less than usual.
 */
export const CONTRACT_ABSENT_NOTE =
  "contract.absent: this build does not publish nav-state; only the legacy " +
  "reachability, depth and search specs ran";

export const NO_CONTRACT_NOTE =
  "contract.absent: this build publishes neither nav-state nor tree-navigator, " +
  "so no spec in this suite could run against it";

/**
 * What the build under test publishes, probed once per worker.
 *
 * Three states, not two, and the third one is the one that matters.
 *
 *   beacon and tree   everything runs.
 *   tree only         a build that predates the nav-state beacon. The legacy
 *                     reachability, depth and search specs still ran against it
 *                     for months, so they run; everything that reads the beacon
 *                     skips with CONTRACT_ABSENT_NOTE.
 *   neither           a build that publishes no part of the contract at all.
 *                     Every spec skips. Reporting fourteen legacy timeouts here
 *                     would be fourteen findings about one absence, and would
 *                     read as fourteen defects in a product that has none of
 *                     them: it simply does not carry the attributes this suite
 *                     drives it through.
 */
interface ContractProbe {
  beacon: boolean;
  tree: boolean;
}
let contractProbe: ContractProbe | null = null;

async function probeContract(page: Page): Promise<ContractProbe> {
  if (contractProbe !== null) return contractProbe;
  await page.goto("/?mode=workbench").catch(() => {});
  // Either signal ends the wait; the absence of both is what has to be
  // distinguishable from a page that simply never loaded, which is why this
  // waits the full boot budget before concluding anything.
  await page
    .waitForSelector('[data-testid="nav-state"], [data-testid="tree-navigator"]', {
      state: "attached",
      timeout: 60_000,
    })
    .catch(() => {});
  contractProbe = {
    beacon: (await page.locator('[data-testid="nav-state"]').count()) > 0,
    tree: (await page.locator('[data-testid="tree-navigator"]').count()) > 0
      || (await page.locator('[data-testid="tree-expand"]').count()) > 0,
  };
  return contractProbe;
}

/**
 * Call at the top of any case that reads the beacon. Skips with the annotation
 * when the build cannot answer, and returns having done nothing when it can.
 */
export async function requireContract(page: Page): Promise<void> {
  const probe = await probeContract(page);
  if (probe.beacon) return;
  const note = probe.tree ? CONTRACT_ABSENT_NOTE : NO_CONTRACT_NOTE;
  test.info().annotations.push({ type: "coverage", description: note });
  test.skip(true, note);
}

/**
 * Call at the top of the legacy specs, which predate the beacon and need only
 * the tree. They run against an older build; they cannot run against one that
 * publishes nothing.
 */
export async function requireLegacyContract(page: Page): Promise<void> {
  const probe = await probeContract(page);
  if (probe.beacon || probe.tree) return;
  test.info().annotations.push({ type: "coverage", description: NO_CONTRACT_NOTE });
  test.skip(true, NO_CONTRACT_NOTE);
}

export const test = base.extend<{
  contract: Contract;
  recorder: Recorder;
  crawlPage: Page;
}>({
  contract: [
    // eslint-disable-next-line no-empty-pattern
    async ({}, use) => {
      await use(loadContract());
    },
    { scope: "worker" },
  ],

  crawlPage: async ({ page }, use) => {
    // The first-visit orientation covers the page. Dismissed before any script
    // runs rather than clicked away per test, so no case depends on being the
    // first one in its shard (a rule the AI plan had to state in prose).
    await page.addInitScript(
      ([key]) => {
        try {
          window.localStorage.setItem(key, "true");
        } catch {
          /* storage unavailable; the overlay is then handled per case */
        }
      },
      [ORIENTATION_DISMISSED_KEY],
    );
    await use(page);
  },

  recorder: async ({ crawlPage }, use) => {
    const allowed = allowedErrorPaths();
    const consoleErrors: string[] = [];
    const failedRequests: string[] = [];

    crawlPage.on("console", (msg: ConsoleMessage) => {
      if (msg.type() !== "error") return;
      const text = msg.text();
      const location = msg.location()?.url ?? "";
      if (isAllowed(text, allowed) || isAllowed(location, allowed)) return;
      consoleErrors.push(text);
    });
    crawlPage.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));
    crawlPage.on("response", (res) => {
      if (res.status() < 400) return;
      if (isAllowed(res.url(), allowed)) return;
      failedRequests.push(`${res.status()} ${res.url()}`);
    });

    const recorder: Recorder = {
      consoleErrors,
      failedRequests,
      reset() {
        consoleErrors.length = 0;
        failedRequests.length = 0;
      },
      problems() {
        return [...consoleErrors, ...failedRequests];
      },
    };
    await use(recorder);
  },
});

export { expect };

/**
 * Wait for the app to have finished booting.
 *
 * ATTACHED, not visible, and the beacon FIRST. Two lessons are folded into
 * those four words, both paid for by a run where every case timed out against a
 * perfectly healthy page.
 *
 * The first: below the lg breakpoint the tree lives in a drawer behind the
 * header's hamburger, so it is in the DOM and correctly invisible until the
 * reader opens it. Waiting for visibility failed every mobile case for sixty
 * seconds each.
 *
 * The second: the tree stopped being a reliable boot signal at all. The
 * workbench now defaults to the "focused" density, and `leftCollapsed`
 * initialises from it, so the sidebar starts collapsed and `TreeNavigator` is
 * not rendered until the reader expands it. A wait anchored on the tree was
 * really a wait on a layout default, and when the default moved the wait
 * reported the product as dead.
 *
 * The beacon is the honest anchor: it is always mounted, in both apertures, and
 * its whole job is to say the app is up and where it is. The tree is kept as an
 * alternative for builds that predate the beacon, which is exactly the case the
 * contract-presence gate then has to recognise.
 */
export async function waitForBoot(page: Page, timeout: number): Promise<void> {
  await page.waitForSelector('[data-testid="nav-state"], [data-testid="tree-navigator"]', {
    state: "attached",
    timeout,
  });
}

/**
 * Make the tree navigator available, the way a reader would.
 *
 * The sidebar is collapsed by default under the focused density, and on a phone
 * it is a drawer, so the tree is genuinely absent from the DOM until it is
 * asked for. That is a layout decision, not a defect: the "Expand sidebar"
 * control and the header's hamburger both exist and both work. A spec that
 * needs a tree row therefore opens the tree first, once, rather than reporting
 * a collapsed panel as an unreachable component.
 *
 * Returns whether a tree is now available, so a caller can say so instead of
 * asserting into thin air.
 */
export async function ensureTree(page: Page): Promise<boolean> {
  if ((await page.locator('[data-testid="tree-navigator"]').count()) > 0) return true;
  const expand = page.locator('[data-testid="tree-expand"]');
  for (let i = 0; i < (await expand.count()); i++) {
    const control = expand.nth(i);
    if (!(await control.isVisible().catch(() => false))) continue;
    await control.click({ timeout: 10_000 }).catch(() => {});
    const appeared = await page
      .waitForSelector('[data-testid="tree-navigator"]', { state: "attached", timeout: 10_000 })
      .then(() => true)
      .catch(() => false);
    if (appeared) return true;
  }
  return (await page.locator('[data-testid="tree-navigator"]').count()) > 0;
}

/**
 * Build the query string, defaulting the aperture to the workbench.
 *
 * A fresh origin now lands on the Overview front door, which is the right
 * default for a reader and the wrong one for six specs written about the
 * workbench: reachability, depth, search, graph, journeys and tours would each
 * spend their first assertion discovering they were somewhere else. So every
 * navigation says which aperture it means, and a caller who passes `mode`
 * (overview.spec, and the boot case that checks the default) always wins.
 *
 * Saying it explicitly rather than clicking through Overview is deliberate: the
 * workbench specs are about the workbench, and the transition between the two
 * apertures is overview.spec's subject, tested once and properly.
 */
function queryFor(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  const withMode = "mode" in params ? params : { ...params, mode: "workbench" };
  for (const [key, value] of Object.entries(withMode)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  return search.toString();
}

/**
 * COLD navigation: a real page load at a real URL, as a pasted deep link is.
 *
 * Use this where arriving from outside is the thing under test. It is the
 * honest way to check a deep link, and it is expensive by nature: on private large-repository validation corpus
 * the app parses a 29 MB manifest on every load, so a sweep built entirely
 * out of cold loads is an hour-scale job.
 */
export async function gotoState(
  page: Page,
  params: Record<string, string | number | undefined>,
): Promise<void> {
  const query = queryFor(params);
  await page.goto(query ? `/?${query}` : "/");
  await waitForBoot(page, 60_000);
}

/**
 * WARM navigation: move within the already-loaded app, as a reader does.
 *
 * Pushes the URL and fires popstate, which useUrlSync listens for and applies
 * to the store. The dataset stays parsed, so a sweep costs a render rather than
 * a re-parse of tens of megabytes.
 *
 * This is not merely the fast version of gotoState. Cold arrival and warm
 * in-app movement are different code paths and either can break alone, so the
 * suite deliberately uses cold loads where arriving from outside is the claim
 * and warm moves everywhere else.
 */
export async function navigateState(
  page: Page,
  params: Record<string, string | number | undefined>,
): Promise<void> {
  // "Booted" is asked of the beacon, not the tree.
  //
  // The tree is collapsed by default under the focused density, so a check for
  // it answered "not booted" on every call and every warm navigation silently
  // became a cold one. The suite still passed and simply got slower, which is
  // the worst kind of harness bug: it changes what is being measured and says
  // nothing about it.
  const booted = await page.locator('[data-testid="nav-state"]').count();
  if (booted === 0) {
    await gotoState(page, params);
    return;
  }
  const query = queryFor(params);
  await page.evaluate((q: string) => {
    window.history.pushState({}, "", q ? `/?${q}` : "/");
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, query);
  await waitForBoot(page, 30_000);
}

/**
 * Record a finding: a distinct problem, and every instance of it.
 *
 * The crawl used to report only a verdict, so "1 failed" was all a reader got
 * from a sweep over hundreds of components. That says almost nothing. What
 * matters is how many things were wrong and whether they are one problem seen
 * many times or many separate problems, because those call for completely
 * different responses and look identical in a pass/fail tally.
 *
 * Called BEFORE the assertion, so the accounting survives even when the
 * assertion throws and ends the case.
 */
/**
 * Record a fact about what this build exposes, for `discovery.json`.
 *
 * Separate from findings on purpose. A finding says something is wrong; a
 * discovery says what is there, whether or not anything is wrong with it. The
 * run record has always carried the first and never the second, so every later
 * consumer that wanted to know "which lenses does this version offer" had to
 * re-derive it by running the suite again and reading prose.
 *
 * Emitted as an annotation for the same reason findings are: it survives an
 * assertion that throws, so a case that fails still contributes what it had
 * already learned.
 */
export function reportDiscovery(key: string, value: unknown): void {
  test.info().annotations.push({
    type: "discovery",
    description: JSON.stringify({ key, value }),
  });
}

export function reportFinding(
  rule: string,
  items: string[],
  opts: { severity?: "error" | "warn"; title?: string } = {},
): void {
  if (items.length === 0) return;
  test.info().annotations.push({
    type: "finding",
    description: JSON.stringify({
      rule,
      severity: opts.severity ?? "error",
      title: opts.title ?? `${rule}: ${items.length} instance(s)`,
      instances: items.length,
      examples: items.slice(0, 5),
    }),
  });
}

/** CSS attribute-selector escaping; CSS.escape is not available out here. */
export function cssEscape(value: string): string {
  return value.replace(/["\\]/g, "\\$&");
}

export interface ExpansionWalk {
  /** Every component id that appeared in the tree during the walk. */
  seen: Set<string>;
  /** Passes taken to converge. */
  passes: number;
  converged: boolean;
}

/**
 * Open the whole tree, adaptively.
 *
 * Reads what is currently collapsed, opens each of those BY IDENTITY, and
 * repeats until a pass finds nothing new to open. The tree's width and depth
 * are unknown by design, so the loop terminates on convergence rather than on
 * a shape the test assumed.
 *
 * Clicking by identity rather than by index is load bearing: expanding one node
 * reflows every row below it, so an index-driven walk clicks the wrong element
 * or waits forever on one that has detached.
 */
export async function expandWholeTree(page: Page, maxPasses = 60): Promise<ExpansionWalk> {
  const seen = new Set<string>();
  const openedFolders = new Set<string>();
  const openedNodes = new Set<string>();
  let passes = 0;

  for (; passes < maxPasses; passes++) {
    for (const id of await page
      .locator('[data-testid="tree-node"]')
      .evaluateAll((els) => els.map((el) => el.getAttribute("data-component-id") ?? ""))) {
      if (id) seen.add(id);
    }

    // Folder groups first: the "Internal Components" section hides whole
    // subtrees behind a collapsed folder, and a walk that never opens them
    // reports a tree far smaller than the data.
    const folderNames = (
      await page
        .locator('[data-testid="tree-folder"][data-expanded="false"]')
        .evaluateAll((els) => els.map((el) => el.getAttribute("data-folder-name") ?? ""))
    ).filter((n) => n && !openedFolders.has(n));
    const collapsedIds = (
      await page
        .locator('[data-testid="tree-node"][data-expanded="false"]')
        .evaluateAll((els) => els.map((el) => el.getAttribute("data-component-id") ?? ""))
    ).filter((id) => id && !openedNodes.has(id));

    if (folderNames.length === 0 && collapsedIds.length === 0) {
      return { seen, passes, converged: true };
    }

    for (const name of folderNames) {
      openedFolders.add(name);
      const folder = page.locator(
        `[data-testid="tree-folder"][data-folder-name="${cssEscape(name)}"]`,
      );
      if ((await folder.count()) === 0) continue;
      if ((await folder.first().getAttribute("data-expanded")) === "false") {
        await folder.first().click();
      }
    }
    for (const id of collapsedIds) {
      openedNodes.add(id);
      const node = page.locator(`[data-testid="tree-node"][data-component-id="${cssEscape(id)}"]`);
      if ((await node.count()) === 0) continue;
      if ((await node.first().getAttribute("data-expanded")) === "false") {
        await node.first().locator('[data-testid="tree-node-toggle"]').click();
      }
    }
  }
  return { seen, passes, converged: false };
}

/** The error boundary rendering anywhere is a failure, whatever else is true. */
export async function expectNoErrorBoundary(page: Page): Promise<void> {
  const boundary = page.locator('[role="alert"]');
  const count = await boundary.count();
  if (count === 0) return;
  const texts: string[] = [];
  for (let i = 0; i < count; i++) {
    texts.push((await boundary.nth(i).innerText()).trim());
  }
  const real = texts.filter((t) => /error|failed|something went wrong/i.test(t));
  expect(real, `error boundary rendered: ${real.join(" | ")}`).toHaveLength(0);
}

// ── The navigation-state beacon ──────────────────────────────────────────────

/**
 * Everything the app publishes about where it is, read in one go.
 *
 * The beacon is read as a whole rather than field by field because the checks
 * that matter are cross-field: "a tour is active but nothing is selected" and
 * "the beacon says reset while a panel is up" are only visible when the fields
 * are compared against each other and against the DOM at the same instant.
 */
export interface NavState {
  /** Which aperture published this state: overview or workbench. */
  mode: string;
  /** The semantic altitude: system, domain or component. */
  level: string;
  /** The Overview direction: portrait, questions or atlas. */
  direction: string;
  /** "true" when this workbench was arrived at from Overview. */
  handoff: string;
  drill: string;
  selected: string;
  lens: string;
  flow: string;
  flowStep: string;
  capability: string;
  entity: string;
  rule: string;
  finding: string;
  tour: string;
  tourStep: string;
  orientation: string;
  orientationStep: string;
  orientationInvite: string;
  orientationSkipped: string;
  panel: string;
  detail: string;
  overlays: string[];
  blast: string;
}

/** The fields that must all be empty at rest, in the order a report reads best. */
export const RESET_FIELDS = [
  "drill",
  "selected",
  "flow",
  "capability",
  "entity",
  "rule",
  "finding",
  "tour",
] as const;

export async function readNavState(page: Page): Promise<NavState> {
  const beacon = page.locator('[data-testid="nav-state"]');
  // Node-enforced: the beacon is always mounted, so waiting for it here turns a
  // page that never finished booting into a timeout with a name on it rather
  // than a pile of "expected '' received null" further down.
  await beacon.waitFor({ state: "attached", timeout: 30_000 });
  const raw = await beacon.first().evaluate((el) => ({
    mode: el.getAttribute("data-mode") ?? "",
    level: el.getAttribute("data-level") ?? "",
    direction: el.getAttribute("data-direction") ?? "",
    handoff: el.getAttribute("data-handoff") ?? "",
    drill: el.getAttribute("data-drill") ?? "",
    selected: el.getAttribute("data-selected") ?? "",
    lens: el.getAttribute("data-lens") ?? "",
    flow: el.getAttribute("data-flow") ?? "",
    flowStep: el.getAttribute("data-flow-step") ?? "",
    capability: el.getAttribute("data-capability") ?? "",
    entity: el.getAttribute("data-entity") ?? "",
    rule: el.getAttribute("data-rule") ?? "",
    finding: el.getAttribute("data-finding") ?? "",
    tour: el.getAttribute("data-tour") ?? "",
    tourStep: el.getAttribute("data-tour-step") ?? "",
    orientation: el.getAttribute("data-orientation") ?? "",
    orientationStep: el.getAttribute("data-orientation-step") ?? "",
    orientationInvite: el.getAttribute("data-orientation-invite") ?? "",
    orientationSkipped: el.getAttribute("data-orientation-skipped") ?? "",
    panel: el.getAttribute("data-panel") ?? "",
    detail: el.getAttribute("data-detail") ?? "",
    overlays: el.getAttribute("data-overlays") ?? "",
    blast: el.getAttribute("data-blast") ?? "",
  }));
  return { ...raw, overlays: raw.overlays ? raw.overlays.split(",") : [] };
}

/** The navigation fields alone: what "opening an overlay changed nothing" means. */
export function navFields(state: NavState): Record<string, string> {
  return {
    // The aperture and the altitude are navigation: a surface that dropped the
    // reader from the workbench to Overview, or moved them from domain to
    // system, has moved them, whatever it left the drill at.
    mode: state.mode,
    level: state.level,
    drill: state.drill,
    selected: state.selected,
    lens: state.lens,
    flow: state.flow,
    flowStep: state.flowStep,
    capability: state.capability,
    entity: state.entity,
    rule: state.rule,
    finding: state.finding,
    tour: state.tour,
    tourStep: state.tourStep,
  };
}

/** The URL's query parameters, as the reader would see them in the address bar. */
export async function readUrlParams(page: Page): Promise<URLSearchParams> {
  return new URLSearchParams(new URL(page.url()).search);
}

// ── The reset probe ─────────────────────────────────────────────────────────

/** The dialog roots that must all be gone once a journey is over. */
const DIALOG_ROOTS = [
  "search-overlay",
  "findings-surface",
  "supply-chain-surface",
  "inventory-panel",
  "tours-list-overlay",
  "help-overlay",
  "tour-step-panel",
  "trust-drawer",
  "preferences-drawer",
  "orientation-walk",
  "orientation-invite",
];

/**
 * Return to the start the way a reader would, then assert that nothing of the
 * journey survived.
 *
 * This is the whole point of the journeys spec, and it is the owner's first
 * named defect class: you drill into a context, go back to the start, and
 * something from the old context is still in force. The residue is usually
 * invisible on screen, which is why it survives manual testing: a stale
 * `capability=` in the URL or a lens-scoped selection nothing renders will
 * quietly change what the NEXT thing you click does.
 *
 * Both halves are asserted deliberately. The beacon says what the store thinks;
 * the DOM says what the reader can see. A beacon claiming a clean slate while a
 * tour panel is still on screen is a failure, and checking only one of the two
 * would miss it in one direction or the other.
 *
 * Returns the residue rather than throwing, so a journey loop can record and
 * continue; the caller reports `journey.context_leak` and then asserts.
 */
export async function resetProbe(page: Page, label: string): Promise<string[]> {
  // Home if we are drilled, exactly as a reader would leave: the button is the
  // affordance the app offers, so using history or a bare URL here would test a
  // route nobody takes. Home also clears the selection (navigateToBreadcrumb
  // sets selectedComponentId to null).
  const home = page.locator('[data-testid="drill-home"]');
  if ((await home.count()) > 0) {
    await home.first().click({ timeout: 15_000 }).catch(() => {});
  }
  // Twice: one Escape closes the innermost surface (a tour, say) and the second
  // closes whatever that revealed. Two is what a person does.
  await page.keyboard.press("Escape").catch(() => {});
  await page.keyboard.press("Escape").catch(() => {});

  // Settling is Node-enforced and bounded. Waiting for the drill to clear is
  // the honest signal that the Home click landed; a fixed sleep would pass on a
  // page that never processed the click at all.
  await expect
    .poll(async () => (await readNavState(page)).drill, { timeout: 5_000, intervals: [100] })
    .toBe("")
    .catch(() => {});

  // The lens, back to the default, through the switcher. Home and Escape are
  // the design's two named gestures and neither touches the lens; a reader who
  // wanted to be back at the start would use the control that put them in the
  // lens in the first place. Leaving it out would mean every journey through a
  // lens reported the lens itself as residue, which says nothing.
  if ((await readNavState(page)).lens !== "structure") {
    const select = page.locator('[data-testid="lens-select"]');
    if ((await select.count()) > 0) {
      await select.first().selectOption("structure", { timeout: 15_000 }).catch(() => {});
      await expect
        .poll(async () => (await readNavState(page)).lens, { timeout: 10_000 })
        .toBe("structure")
        .catch(() => {});
    }
  }

  // The selection, cleared by clicking the empty canvas.
  //
  // This was written when Escape did NOT close the detail panel and the design
  // assumed it did. App.tsx now registers the global Escape handler the help
  // dialog always advertised, last in the chain behind every overlay's own, so
  // the two Escapes above usually clear the selection on their own. The pane
  // click stays because it is the product's other named gesture for it
  // (ArchitectureGraph's onPaneClick calls selectComponent(null)), it is a
  // route a reader genuinely takes, and a probe that depended on one gesture
  // would report the other's absence as residue from every journey. The
  // Escape promise itself is held separately, by name, in journeys.spec.
  if ((await readNavState(page)).selected !== "") {
    const pane = page.locator(".react-flow__pane");
    const box = await pane.first().boundingBox().catch(() => null);
    if (box) {
      await page.mouse.click(box.x + 8, box.y + box.height - 8);
      await expect
        .poll(async () => (await readNavState(page)).selected, { timeout: 10_000 })
        .toBe("")
        .catch(() => {});
    }
  }

  const residue: string[] = [];
  const state = await readNavState(page);
  // The workbench specs' "start" is the workbench root, not the front door.
  // A journey that silently dropped the reader back to Overview would leave
  // every other field trivially clean, so the aperture is checked first.
  if (state.mode !== "workbench") {
    residue.push(
      `${label}: the reset left the reader in the "${state.mode}" aperture rather than the ` +
        `workbench the journey started in`,
    );
  }
  for (const field of RESET_FIELDS) {
    if (state[field] !== "") {
      residue.push(`${label}: ${field}="${state[field]}" survived the reset`);
    }
  }
  if (state.lens !== "structure") {
    residue.push(`${label}: lens="${state.lens}" survived the reset`);
  }
  if (state.overlays.length > 0) {
    residue.push(`${label}: overlays "${state.overlays.join(",")}" still open after the reset`);
  }

  // The visible half. A field can read clean while its surface is still up, and
  // this is the direction that actually happens: the beacon reports nothing
  // selected because the store cleared selectedComponentId, while the panel is
  // still mounted showing the component from the journey.
  const panel = page.locator('[data-testid="detail-panel"]');
  if ((await panel.count()) > 0) {
    const shown = await panel.first().getAttribute("data-component-id");
    residue.push(
      `${label}: the detail panel for "${shown ?? "?"}" is still on screen after the reset, ` +
        `while the beacon reports selected="${state.selected}" and panel="${state.panel}"`,
    );
  }
  for (const testId of DIALOG_ROOTS) {
    if ((await page.locator(`[data-testid="${testId}"]`).count()) > 0) {
      residue.push(`${label}: ${testId} is still on screen after the reset`);
    }
  }

  // A bare URL. `data` is the multi-repo data-source override, which is part of
  // the address of the dataset itself rather than of a journey through it, so
  // it legitimately survives (see buildUrl in utils/urlState.ts).
  const params = await readUrlParams(page);
  // `data` is the multi-repo data-source override and `mode` is the aperture:
  // both are part of the ADDRESS of what the reader is looking at rather than
  // of a journey through it, and the app writes `mode` on every URL it builds.
  // Everything else is residue.
  const leftovers = [...params.keys()].filter((k) => k !== "data" && k !== "mode");
  if (leftovers.length > 0) {
    residue.push(`${label}: URL still carries ${leftovers.join(", ")} after the reset`);
  }
  return residue;
}

// ── Geometry ────────────────────────────────────────────────────────────────

/**
 * Whether a node is fully inside the canvas, computed from Node.
 *
 * Both boxes come back through locator.boundingBox(), so the arithmetic happens
 * here rather than in a page.evaluate that carries no timeout (the lesson the
 * lens sweep paid for). The 2px tolerance is for the subpixel rounding a CSS
 * transform leaves behind: a node one third of a pixel outside the frame is
 * fully visible to a reader, and calling it a defect would be the harness
 * inventing one.
 */
export const IN_VIEW_TOLERANCE_PX = 2;

export async function isFullyInView(
  page: Page,
  nodeSelector: string,
  canvasSelector = ".react-flow",
): Promise<boolean> {
  const node = await page.locator(nodeSelector).first().boundingBox();
  const canvas = await page.locator(canvasSelector).first().boundingBox();
  if (!node || !canvas) return false;
  const t = IN_VIEW_TOLERANCE_PX;
  return (
    node.x >= canvas.x - t &&
    node.y >= canvas.y - t &&
    node.x + node.width <= canvas.x + canvas.width + t &&
    node.y + node.height <= canvas.y + canvas.height + t
  );
}

/**
 * Wait up to `timeout` for a node to be fully inside the canvas.
 *
 * expect.poll rather than a raw loop: the wait is enforced from Node, so a page
 * too busy to answer fails the case instead of hanging it.
 */
export async function waitForInView(
  page: Page,
  nodeSelector: string,
  timeout = 2_000,
): Promise<boolean> {
  try {
    await expect
      .poll(() => isFullyInView(page, nodeSelector), { timeout, intervals: [100] })
      .toBe(true);
    return true;
  } catch {
    return false;
  }
}

/**
 * Wait until an element has stopped moving, then report whether it did.
 *
 * The graph re-lays out after every drill: elk runs, the view fits with a 400ms
 * animation, and 420ms later a readability check can shrink the node budget and
 * start the whole thing again. Playwright checks actionability once, before the
 * first click of a double-click, so a node that is still travelling can slide
 * out from under the second click and the drill silently does not happen.
 *
 * That is the same failure the app itself fixed from the other side
 * (ArchitectureGraph stopped re-centring an already-visible selection because
 * "the second click of a double-click landed on the empty pane instead of the
 * node"). A reader double-clicks a node that has come to rest, so the test does
 * too. Node-enforced and bounded: a canvas that never settles times out here
 * rather than hanging the run.
 */
export async function waitForStableBox(
  page: Page,
  selector: string,
  timeout = 8_000,
): Promise<boolean> {
  const read = async (): Promise<string> => {
    const box = await page.locator(selector).first().boundingBox().catch(() => null);
    return box ? `${Math.round(box.x)},${Math.round(box.y)},${Math.round(box.width)}` : "gone";
  };
  // Sentinel rather than a first reading: seeding with a box taken microseconds
  // earlier would make the very first comparison trivially equal and the helper
  // would return "stable" without ever having waited, which is the failure mode
  // of every stability check written in a hurry.
  let previous = "\u0000";
  try {
    await expect
      .poll(
        async () => {
          const now = await read();
          const stable = now === previous && now !== "gone";
          previous = now;
          return stable;
        },
        // expect.poll enforces the interval from Node, so the two readings
        // being compared are genuinely a quarter of a second apart.
        { timeout, intervals: [250] },
      )
      .toBe(true);
    return true;
  } catch {
    return false;
  }
}

/**
 * The shape of the window the app actually left for its content.
 *
 * Attached to a finding when a click cannot land, because "the row would not
 * accept a click" and "the row is 173px tall inside a 103px panel because the
 * banners above it took 617 of 720 vertical pixels" are the same observation
 * and only the second one is actionable. Reported as a sentence rather than a
 * number so the finding reads as a cause.
 */
export async function describeViewport(page: Page): Promise<string> {
  const viewport = page.viewportSize();
  const main = await page.locator("main").first().boundingBox().catch(() => null);
  const parts = [
    `viewport ${viewport?.width ?? "?"}x${viewport?.height ?? "?"}`,
    main
      ? `main content area ${Math.round(main.width)}x${Math.round(main.height)} starting at y=${Math.round(main.y)}`
      : "no main content area",
  ];
  return parts.join("; ");
}

/**
 * What is actually sitting on an element's click point.
 *
 * "The click timed out" is not a finding; "the row's centre point belongs to
 * the row below it" is. Attached to a failed click so the report names the
 * obstruction instead of the symptom, and it reports the element's own height
 * against the height of the absolutely-positioned slot a windowed list put it
 * in, because a row taller than its slot is the usual reason one row ends up
 * on top of another.
 */
export async function describeObstruction(page: Page, selector: string): Promise<string> {
  return page.locator(selector).first().evaluate((el) => {
    const rect = el.getBoundingClientRect();
    const slot = el.closest("div[style*='position: absolute']") as HTMLElement | null;
    const slotRect = slot?.getBoundingClientRect();
    const cx = rect.x + rect.width / 2;
    const cy = rect.y + rect.height / 2;
    const atPoint = document.elementFromPoint(cx, cy);
    const owner = atPoint?.closest("[data-testid]") as HTMLElement | null;
    const who = owner
      ? `${owner.getAttribute("data-testid")}${
          owner.getAttribute("data-row-id") ? ` "${owner.getAttribute("data-row-id")}"` : ""
        }`
      : atPoint
        ? atPoint.tagName.toLowerCase()
        : "nothing (the point is outside the viewport)";
    const slotNote = slotRect
      ? `; it sits in a ${Math.round(slotRect.height)}px windowed-list slot`
      : "";
    return (
      `the element is ${Math.round(rect.width)}x${Math.round(rect.height)}px${slotNote}, ` +
      `and its centre point belongs to ${who}`
    );
  });
}

/**
 * What is covering a node, or null when nothing is.
 *
 * "The node is inside the canvas box" is not the same claim as "the reader can
 * see the node", and the crawl was only making the first one. A tour panel, a
 * bottom sheet or a drill hint sitting on top of the node the narration is
 * about leaves the geometry perfect and the reader looking at a panel, which is
 * exactly the defect the mobile tour had (GUI crawl 2026-09-01). So the check
 * is the one a reader makes: what does the browser say is at that point.
 *
 * Hit testing is done in one page.evaluate and the answer is a sentence,
 * because a finding that says "occluded" and not by what cannot be acted on.
 * Elements the browser will not hit-test at all (pointer-events: none) are the
 * browser's own answer and are reported as found: something IS painted there.
 */
export async function describeOcclusion(page: Page, selector: string): Promise<string | null> {
  return page.evaluate((sel: string) => {
    const el = document.querySelector(sel);
    if (!el) return "the node is not on the page";
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return "the node has no box";
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    if (x < 0 || y < 0 || x > window.innerWidth || y > window.innerHeight) {
      return "the node's centre is outside the viewport";
    }
    const hit = document.elementFromPoint(x, y);
    if (!hit) return "nothing is hit-testable at the node's centre";
    if (el === hit || el.contains(hit)) return null;
    // Name the cover the way the product names itself, walking out from the
    // element actually hit until something carries an identity attribute. The
    // walk is bounded so a miss reports the tag rather than the document.
    let cur: Element | null = hit;
    for (let i = 0; i < 6 && cur; i++) {
      const id = cur.getAttribute("data-testid") ?? cur.getAttribute("data-se");
      if (id) return `[${id}]`;
      cur = cur.parentElement;
    }
    return `<${hit.tagName.toLowerCase()}>`;
  }, selector);
}

/** What `waitForUnoccluded` found. */
export interface OcclusionResult {
  /** True when the node was still covered once the ceiling was reached. */
  occluded: boolean;
  /** What covered the node on the last read that found a cover, or null if it never was. */
  lastCover: string | null;
  /** How long the node stayed covered: until it cleared, or the ceiling if it never did. */
  coveredForMs: number;
}

/**
 * Poll a node's centre point until nothing else is painted over it, or give up
 * at `ceilingMs`.
 *
 * A single `describeOcclusion` read taken right after the in-view wait passes
 * catches ArchitectureGraph's own pan animation (fitView, 400ms) rather than a
 * defect: at 150ms after a tour step or a selection the node is still travelling
 * and something else legitimately sits where it will end up, and by 600ms it has
 * settled. The same lesson `waitForStableBox` already paid for on click
 * actionability applies here to what a reader can see, so this is `waitForInView`
 * shaped: `expect.poll` at 100ms intervals, Node-enforced, bounded by `ceilingMs`.
 *
 * Not weakened by the retry: a node still covered once the ceiling passes is
 * still a finding, and the result carries what covered it last and how long it
 * stayed covered, so the report reads as a cause rather than a flake.
 */
export async function waitForUnoccluded(
  page: Page,
  selector: string,
  ceilingMs = 2_000,
): Promise<OcclusionResult> {
  const start = Date.now();
  let lastCover: string | null = null;
  let clearedAt: number | null = null;
  try {
    await expect
      .poll(
        async () => {
          const cover = await describeOcclusion(page, selector);
          if (cover) {
            lastCover = cover;
            return false;
          }
          clearedAt = Date.now();
          return true;
        },
        { timeout: ceilingMs, intervals: [100] },
      )
      .toBe(true);
    return { occluded: false, lastCover, coveredForMs: (clearedAt ?? start) - start };
  } catch {
    return { occluded: true, lastCover, coveredForMs: Date.now() - start };
  }
}

/**
 * The visible instance of an entry point, opening whatever hides it.
 *
 * One affordance can have two homes. Below the `sm` breakpoint the workbench's
 * header search and help buttons are `display: none` and the product offers the
 * same two actions from the bottom navigation and the overflow menu instead.
 * Both carry the contract id, because the contract is about the affordance
 * rather than about one element, and only one of them is ever visible.
 *
 * So a spec asks for the one on screen, not the first in DOM order, and if none
 * is on screen it opens the overflow menu once and asks again. That is the
 * gesture a reader makes; a test that clicked the hidden one would report a
 * layout it did not understand as a dead control.
 *
 * Returns null when the affordance genuinely cannot be reached, which is a
 * finding for the caller to name.
 */
export async function visibleEntry(
  page: Page,
  testId: string,
): Promise<import("@playwright/test").Locator | null> {
  const all = page.locator(`[data-testid="${testId}"]`);
  const pick = async () => {
    const count = await all.count();
    for (let i = 0; i < count; i++) {
      const candidate = all.nth(i);
      if (await candidate.isVisible().catch(() => false)) return candidate;
    }
    return null;
  };
  const direct = await pick();
  if (direct) return direct;

  const more = page.locator('[data-testid="more-menu"]');
  if ((await more.count()) > 0 && (await more.first().isVisible().catch(() => false))) {
    await more.first().click({ timeout: 5_000 }).catch(() => {});
    return pick();
  }
  return null;
}

/**
 * Make the detail panel readable, the way a reader would.
 *
 * On a phone the detail panel lives in a bottom sheet that opens at its "peek"
 * snap, and `MobileBottomSheet` renders the panel's content only above peek:
 * collapsed, all it shows is the component's name and "Swipe up for details".
 * So `detail-panel` is genuinely not in the DOM until the sheet is opened, and
 * a spec that just navigated and looked would find nothing and quietly check
 * zero components, which is exactly what happened on the first mobile run of
 * the tab sweep: it reported "0/165 components checked" and passed.
 *
 * Tapping the peek header is the product's own gesture (it calls setSnap
 * "half"), so this opens it that way and then waits for the panel.
 */
export async function ensureDetailPanel(page: Page): Promise<boolean> {
  if ((await page.locator('[data-testid="detail-panel"]').count()) > 0) return true;
  const peek = page.locator('[data-testid="detail-sheet-peek"]');
  if ((await peek.count()) === 0) return false;
  await peek.first().click({ timeout: 5_000 }).catch(() => {});
  return page
    .waitForSelector('[data-testid="detail-panel"]', { state: "attached", timeout: 10_000 })
    .then(() => true)
    .catch(() => false);
}
