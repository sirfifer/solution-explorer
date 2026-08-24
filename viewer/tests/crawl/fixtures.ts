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

const HELP_DISMISSED_KEY = "arch-viz-help-dismissed";

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
    // The first-run help overlay covers the tree. Dismissed before any script
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
      [HELP_DISMISSED_KEY],
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

function queryFor(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  return search.toString();
}

/**
 * COLD navigation: a real page load at a real URL, as a pasted deep link is.
 *
 * Use this where arriving from outside is the thing under test. It is the
 * honest way to check a deep link, and it is expensive by nature: on VS Code
 * the app parses a 29 MB manifest on every load, so a sweep built entirely
 * out of cold loads is an hour-scale job.
 */
export async function gotoState(
  page: Page,
  params: Record<string, string | number | undefined>,
): Promise<void> {
  const query = queryFor(params);
  await page.goto(query ? `/?${query}` : "/");
  // The tree is the app's last boot-blocking render: once it exists, the
  // projection has been fetched and reduced.
  await page.waitForSelector('[data-testid="tree-navigator"]', { timeout: 60_000 });
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
  const booted = await page.locator('[data-testid="tree-navigator"]').count();
  if (booted === 0) {
    await gotoState(page, params);
    return;
  }
  const query = queryFor(params);
  await page.evaluate((q: string) => {
    window.history.pushState({}, "", q ? `/?${q}` : "/");
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, query);
  await page.waitForSelector('[data-testid="tree-navigator"]', { timeout: 30_000 });
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
