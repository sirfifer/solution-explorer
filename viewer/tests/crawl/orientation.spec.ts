/**
 * The first-visit product orientation.
 *
 * These rules prove that the invitation remembers a dismissal, every stop
 * points to a live control, the two-surface crossing lands, Escape cleans up,
 * and Help can replay the walk at any time.
 */

import type { Page } from "@playwright/test";
import {
  expect,
  readNavState,
  reportDiscovery,
  reportFinding,
  resetProbe,
  test,
} from "./fixtures";

const DESKTOP_STOPS = [
  "what-this-is",
  "start-with-a-question",
  "two-views",
  "how-much-was-read",
  "your-tools",
  "the-map",
  "lenses",
  "if-you-get-lost",
] as const;

const MOBILE_STOPS = [
  "what-this-is",
  "start-with-a-question",
  "two-views",
  "your-tools",
  "the-map",
  "lenses",
  "if-you-get-lost-mobile",
] as const;

function expectedStops(page: Page): readonly string[] {
  return (page.viewportSize()?.width ?? 1024) < 640 ? MOBILE_STOPS : DESKTOP_STOPS;
}

async function startWalk(page: Page): Promise<void> {
  await page.goto("/?mode=overview&orientation=start");
  await expect(page.locator('[data-testid="system-overview"]')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('[data-testid="orientation-walk"]')).toBeVisible({ timeout: 15_000 });
}

async function waitForStop(page: Page, id: string): Promise<void> {
  await expect
    .poll(async () => (await readNavState(page)).orientation, {
      timeout: 15_000,
      intervals: [50, 100],
    })
    .toBe(id);
  await expect(page.locator(`[data-testid="orientation-walk"][data-stop="${id}"]`)).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('[data-testid="orientation-card"]')).toBeVisible({ timeout: 15_000 });
}

function overlaps(a: { x: number; y: number; width: number; height: number }, b: { x: number; y: number; width: number; height: number }): boolean {
  return a.x < b.x + b.width
    && a.x + a.width > b.x
    && a.y < b.y + b.height
    && a.y + a.height > b.y;
}

test.use({ actionTimeout: 5_000 });

test.describe("orientation walk", () => {
  test(
    "W1: the first visit invite remembers dismissal",
    { tag: ["@desktop", "@mobile"] },
    async ({ page }) => {
      await page.goto("/?mode=overview");
      await expect(page.locator('[data-testid="orientation-invite"]')).toBeVisible({ timeout: 30_000 });
      await expect(page.locator('[data-testid="orientation-start"]')).toBeVisible();
      await expect(page.locator('[data-testid="orientation-dismiss"]')).toBeVisible();

      await page.locator('[data-testid="orientation-dismiss"]').click();
      await expect(page.locator('[data-testid="orientation-invite"]')).toHaveCount(0);
      expect(await page.evaluate(() => localStorage.getItem("arch-viz-orientation-v1"))).toBe("dismissed");

      await page.reload();
      await expect(page.locator('[data-testid="system-overview"]')).toBeVisible({ timeout: 30_000 });
      await expect(page.locator('[data-testid="orientation-invite"]')).toHaveCount(0);
    },
  );

  test(
    "W2: every stop lands on a visible unoccluded anchor",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage }) => {
      await startWalk(crawlPage);
      const expected = expectedStops(crawlPage);
      const wrong: string[] = [];
      const landed: Array<{ stop: string; anchor: string; anchorRect: string; card: string; highlight: string; highlightStyle: string }> = [];

      for (const [index, id] of expected.entries()) {
        await waitForStop(crawlPage, id);
        const state = await readNavState(crawlPage);
        const walk = crawlPage.locator('[data-testid="orientation-walk"]');
        const anchorId = await walk.getAttribute("data-anchor") ?? "";
        const anchor = crawlPage.locator(`[data-testid="${anchorId}"]`).first();
        await expect
          .poll(async () => (await crawlPage.locator('[data-testid="orientation-highlight"]').boundingBox())?.height ?? 0, {
            timeout: 2_000,
            intervals: [25, 50],
          })
          .toBeGreaterThanOrEqual(44)
          .catch(() => {});
        const anchorBox = await anchor.boundingBox();
        const highlightBox = await crawlPage.locator('[data-testid="orientation-highlight"]').boundingBox();
        const cardBox = await crawlPage.locator('[data-testid="orientation-card"]').boundingBox();
        const viewport = crawlPage.viewportSize();

        if (state.orientationStep !== String(index + 1)) {
          wrong.push(`${id}: the beacon reports step ${state.orientationStep}, expected ${index + 1}`);
        }
        if (!anchorBox || !viewport || anchorBox.y + anchorBox.height <= 0 || anchorBox.y >= viewport.height || anchorBox.x + anchorBox.width <= 0 || anchorBox.x >= viewport.width) {
          wrong.push(`${id}: anchor ${anchorId || "<none>"} does not intersect the viewport`);
        }
        if (!highlightBox || highlightBox.width <= 0 || highlightBox.height < 44) {
          wrong.push(`${id}: the highlight is empty or shorter than 44px`);
        }
        if (highlightBox && cardBox && overlaps(highlightBox, cardBox)) {
          wrong.push(`${id}: the card covers the highlighted target`);
        }
        if (state.orientationSkipped !== "") {
          wrong.push(`${id}: skipped anchors are recorded as ${state.orientationSkipped}`);
        }
        landed.push({
          stop: id,
          anchor: anchorId,
          anchorRect: anchorBox ? `${Math.round(anchorBox.x)},${Math.round(anchorBox.y)} ${Math.round(anchorBox.width)}x${Math.round(anchorBox.height)}` : "missing",
          card: cardBox ? `${Math.round(cardBox.x)},${Math.round(cardBox.y)} ${Math.round(cardBox.width)}x${Math.round(cardBox.height)}` : "missing",
          highlight: highlightBox ? `${Math.round(highlightBox.width)}x${Math.round(highlightBox.height)}` : "missing",
          highlightStyle: await crawlPage.locator('[data-testid="orientation-highlight"]').getAttribute("style") ?? "missing",
        });

        if (index < expected.length - 1) {
          await crawlPage.locator('[data-testid="orientation-next"]').click();
        }
      }

      reportDiscovery("orientation_stops", landed);
      reportFinding("orientation.stop_missed", wrong, {
        title: "orientation stops that do not visibly point to their live control",
      });
      expect(wrong, "orientation stops that do not visibly point to their live control").toEqual([]);
    },
  );

  test(
    "W3: the walk crosses surfaces and ends cleanly",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage }) => {
      await startWalk(crawlPage);
      const expected = expectedStops(crawlPage);
      const wrong: string[] = [];

      for (const [index, id] of expected.entries()) {
        await waitForStop(crawlPage, id);
        const state = await readNavState(crawlPage);
        const expectedMode = id === "the-map" || index > expected.indexOf("the-map")
          ? "workbench"
          : "overview";
        if (state.mode !== expectedMode) wrong.push(`${id}: mode is ${state.mode}, expected ${expectedMode}`);
        if (index < expected.length - 1) {
          await crawlPage.locator('[data-testid="orientation-next"]').click();
        }
      }

      await crawlPage.locator('[data-testid="orientation-done"]').click();
      await expect(crawlPage.locator('[data-testid="orientation-walk"]')).toHaveCount(0);
      await expect(crawlPage.locator('[data-testid="orientation-card"]')).toHaveCount(0);
      const ending = await readNavState(crawlPage);
      if (ending.orientation !== "" || ending.orientationStep !== "") {
        wrong.push(`Done left orientation=${ending.orientation} step=${ending.orientationStep}`);
      }
      const returnControl = crawlPage.locator('[data-testid="open-overview"]:visible');
      if ((await returnControl.count()) === 0) wrong.push("Done leaves no visible way back to Overview");
      wrong.push(...await resetProbe(crawlPage, "orientation Done"));

      reportFinding("orientation.crossing_or_exit_wrong", wrong, {
        title: "an orientation crossing or ending that leaves the reader in the wrong state",
      });
      expect(wrong, "an orientation crossing or ending that leaves the reader in the wrong state").toEqual([]);
    },
  );

  test(
    "W4: Escape dismisses the walk without damaging Overview",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage }) => {
      await startWalk(crawlPage);
      await crawlPage.locator('[data-testid="orientation-next"]').click();
      await crawlPage.locator('[data-testid="orientation-next"]').click();
      await waitForStop(crawlPage, "two-views");
      await crawlPage.keyboard.press("Escape");

      await expect(crawlPage.locator('[data-testid="orientation-walk"]')).toHaveCount(0);
      const state = await readNavState(crawlPage);
      expect(state.orientation).toBe("");
      expect(state.orientationStep).toBe("");
      expect(state.overlays).not.toContain("orientation");
      expect(await crawlPage.evaluate(() => localStorage.getItem("arch-viz-orientation-v1"))).toBe("dismissed");
      await expect(crawlPage.locator('[data-testid="question-routes"]')).toBeVisible();
    },
  );

  test(
    "W5: Help replays the walk from the Overview",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage }) => {
      await crawlPage.goto("/?mode=workbench");
      await expect(crawlPage.locator('[data-testid="graph-frame"]')).toBeVisible({ timeout: 30_000 });
      if ((crawlPage.viewportSize()?.width ?? 1024) < 640) {
        await crawlPage.locator('[data-testid="more-menu"]').click();
      }
      await crawlPage.locator('[data-testid="help-button"]:visible').click();
      await expect(crawlPage.locator('[data-testid="help-overlay"]')).toBeVisible();
      await crawlPage.locator('[data-testid="orientation-replay"]').click();
      await waitForStop(crawlPage, "what-this-is");
      expect((await readNavState(crawlPage)).mode).toBe("overview");
    },
  );
});
