/**
 * The first-visit product orientation.
 *
 * These rules prove that a first visit starts with a skippable, centered
 * project orientation, every later stop points to a live control, the
 * two-surface crossing lands, Escape cleans up, and Help can replay the walk.
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
  "how-much-was-analyzed",
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
    "W1: a first visit starts with a centered project orientation and remembers Skip",
    { tag: ["@desktop", "@mobile"] },
    async ({ page }) => {
      await page.goto("/?mode=overview");
      const walk = page.locator('[data-testid="orientation-walk"][data-stop="what-this-is"]');
      const card = page.locator('[data-testid="orientation-card"]');
      await expect(walk).toBeVisible({ timeout: 30_000 });
      await expect(page.locator('[data-testid="orientation-invite"]')).toHaveCount(0);
      await expect(card.locator('[data-testid="orientation-welcome-pair"]')).toContainText("Visual Studio Code");
      await expect(card.locator('[data-testid="orientation-welcome-pair"]')).toContainText("SysCorpus");
      await expect(card.locator('[data-testid="orientation-subject-link"]')).toHaveAttribute("href", "https://code.visualstudio.com/");
      await expect(card.locator('[data-testid="orientation-subject-link"]')).toHaveAttribute("target", "_blank");
      await expect(card.locator('[data-testid="orientation-syscorpus-link"]')).toHaveAttribute("href", "https://syscorpus.com/");
      await expect(card.locator('[data-testid="orientation-syscorpus-link"]')).toHaveAttribute("target", "_blank");
      await expect(page.locator('[data-testid="orientation-exit"]')).toHaveText("Skip");
      const bounds = await card.boundingBox();
      const viewport = await page.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight }));
      expect(bounds && viewport ? Math.abs(bounds.x + bounds.width / 2 - viewport.width / 2) : 999).toBeLessThan(12);
      // Mobile WebKit reserves an 18px safe-area strip, so its usable visual
      // centre is 9px above the raw viewport midpoint.
      expect(bounds && viewport ? Math.abs(bounds.y + bounds.height / 2 - viewport.height / 2) : 999).toBeLessThan(12);

      await page.locator('[data-testid="orientation-exit"]').click();
      await expect(page.locator('[data-testid="orientation-invite"]')).toHaveCount(0);
      await expect(page.locator('[data-testid="orientation-walk"]')).toHaveCount(0);
      expect(await page.evaluate(() => localStorage.getItem("arch-viz-orientation-v1"))).toBe("dismissed");

      await page.reload();
      await expect(page.locator('[data-testid="system-overview"]')).toBeVisible({ timeout: 30_000 });
      await expect(page.locator('[data-testid="orientation-invite"]')).toHaveCount(0);
      await expect(page.locator('[data-testid="orientation-walk"]')).toHaveCount(0);
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
        if (id !== "what-this-is") {
          await expect
            .poll(async () => (await crawlPage.locator('[data-testid="orientation-highlight"]').boundingBox())?.height ?? 0, {
              timeout: 2_000,
              intervals: [25, 50],
            })
            .toBeGreaterThanOrEqual(44)
            .catch(() => {});
        }
        const anchorBox = await anchor.boundingBox();
        const highlightBox = id === "what-this-is"
          ? null
          : await crawlPage.locator('[data-testid="orientation-highlight"]').boundingBox();
        const cardBox = await crawlPage.locator('[data-testid="orientation-card"]').boundingBox();
        const viewport = crawlPage.viewportSize();
        const visibleViewport = await crawlPage.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight }));

        if (state.orientationStep !== String(index + 1)) {
          wrong.push(`${id}: the beacon reports step ${state.orientationStep}, expected ${index + 1}`);
        }
        if (!anchorBox || !viewport || anchorBox.y + anchorBox.height <= 0 || anchorBox.y >= viewport.height || anchorBox.x + anchorBox.width <= 0 || anchorBox.x >= viewport.width) {
          wrong.push(`${id}: anchor ${anchorId || "<none>"} does not intersect the viewport`);
        }
        if (id === "what-this-is" && (await crawlPage.locator('[data-testid="orientation-welcome-backdrop"]').count()) !== 1) {
          wrong.push(`${id}: the centered welcome backdrop is missing`);
        }
        if (id === "what-this-is" && cardBox && (
          Math.abs(cardBox.x + cardBox.width / 2 - visibleViewport.width / 2) >= 12
          || Math.abs(cardBox.y + cardBox.height / 2 - visibleViewport.height / 2) >= 12
        )) {
          wrong.push(`${id}: the opening card is not centered in the viewport`);
        }
        if (id !== "what-this-is" && (!highlightBox || highlightBox.width <= 0 || highlightBox.height < 44)) {
          wrong.push(`${id}: the highlight is empty or shorter than 44px`);
        }
        if (id !== "what-this-is" && highlightBox && cardBox && overlaps(highlightBox, cardBox)) {
          wrong.push(`${id}: the card covers the highlighted target`);
        }
        if (state.orientationSkipped !== "") {
          wrong.push(`${id}: skipped anchors are recorded as ${state.orientationSkipped}`);
        }
        if (id === "your-tools") {
          const menu = crawlPage.locator('[data-testid="theme-menu"]');
          if (!(await menu.isVisible().catch(() => false))) wrong.push(`${id}: the theme choices are not expanded`);
          const menuBox = await menu.boundingBox().catch(() => null);
          if (menuBox && cardBox && overlaps(menuBox, cardBox)) wrong.push(`${id}: the tour card covers the expanded theme choices`);
          if (menuBox && highlightBox && highlightBox.width - menuBox.width > 20) {
            wrong.push(`${id}: the main spotlight is not tightly fitted to the expanded theme menu`);
          }
          const origin = crawlPage.locator('[data-testid="orientation-origin-highlight"]');
          if (!(await origin.isVisible().catch(() => false))) wrong.push(`${id}: the theme control has no separate origin highlight`);
          if ((await crawlPage.locator('[data-testid="orientation-origin-label"]').innerText().catch(() => "")).toLowerCase() !== "theme control") wrong.push(`${id}: the origin is not labeled as the Theme control`);
        } else if ((await crawlPage.locator('[data-testid="theme-menu"]').count()) > 0) {
          wrong.push(`${id}: the theme choices stayed expanded after their stop`);
        }
        if (id === "lenses") {
          const menu = crawlPage.locator('[data-testid="lens-menu"]');
          if (!(await menu.isVisible().catch(() => false))) wrong.push(`${id}: the lens choices are not expanded`);
          const menuBox = await menu.boundingBox().catch(() => null);
          if (menuBox && cardBox && overlaps(menuBox, cardBox)) wrong.push(`${id}: the tour card covers the expanded lens choices`);
          if (menuBox && highlightBox && highlightBox.width - menuBox.width > 20) {
            wrong.push(`${id}: the main spotlight is not tightly fitted to the expanded lens menu`);
          }
          const origin = crawlPage.locator('[data-testid="orientation-origin-highlight"]');
          if (!(await origin.isVisible().catch(() => false))) wrong.push(`${id}: the lens control has no separate origin highlight`);
          if ((await crawlPage.locator('[data-testid="orientation-origin-label"]').innerText().catch(() => "")).toLowerCase() !== "lens control") wrong.push(`${id}: the origin is not labeled as the Lens control`);
        } else if ((await crawlPage.locator('[data-testid="lens-menu"]').count()) > 0) {
          wrong.push(`${id}: the lens choices stayed expanded after their stop`);
        }
        landed.push({
          stop: id,
          anchor: anchorId,
          anchorRect: anchorBox ? `${Math.round(anchorBox.x)},${Math.round(anchorBox.y)} ${Math.round(anchorBox.width)}x${Math.round(anchorBox.height)}` : "missing",
          card: cardBox ? `${Math.round(cardBox.x)},${Math.round(cardBox.y)} ${Math.round(cardBox.width)}x${Math.round(cardBox.height)}` : "missing",
          highlight: highlightBox ? `${Math.round(highlightBox.width)}x${Math.round(highlightBox.height)}` : "missing",
          highlightStyle: id === "what-this-is"
            ? "centered welcome backdrop"
            : await crawlPage.locator('[data-testid="orientation-highlight"]').getAttribute("style") ?? "missing",
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
        if (id === "the-map") {
          await expect
            .poll(async () => crawlPage.locator(".react-flow__node").count(), {
              timeout: 30_000,
              intervals: [100],
              message: "the Workbench map should contain rendered project nodes during the tour",
            })
            .toBeGreaterThan(0);
        }
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
      if (ending.mode !== "overview") wrong.push(`Done leaves the reader in ${ending.mode}, expected overview`);
      await expect(crawlPage.locator('[data-testid="system-overview"]')).toBeVisible();
      await crawlPage.locator('[data-testid="open-workbench"]').first().click();
      await expect
        .poll(async () => (await readNavState(crawlPage)).mode, { timeout: 15_000 })
        .toBe("workbench");
      await expect
        .poll(async () => crawlPage.locator(".react-flow__node:visible").count(), {
          timeout: 30_000,
          intervals: [100],
          message: "the Workbench map should still render after the orientation ends",
        })
        .toBeGreaterThan(0);
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
      await expect
        .poll(async () => (await readNavState(crawlPage)).mode, { timeout: 30_000 })
        .toBe("workbench");
      const helpButton = crawlPage.locator('[data-testid="help-button"]:visible');
      await expect(helpButton).toBeVisible({ timeout: 15_000 });
      await expect(helpButton).toHaveText(/Help/);
      const helpBox = await helpButton.boundingBox();
      const viewport = crawlPage.viewportSize();
      expect(helpBox && viewport ? helpBox.y : 999).toBeLessThan(200);
      expect(helpBox && viewport ? viewport.width - helpBox.x - helpBox.width : 999).toBeLessThan(180);
      await helpButton.click();
      await expect(crawlPage.locator('[data-testid="help-overlay"]')).toBeVisible();
      const replay = crawlPage.locator('[data-testid="orientation-replay"]');
      await expect(replay).toHaveText("Replay guided tour");
      await replay.click();
      await waitForStop(crawlPage, "what-this-is");
      expect((await readNavState(crawlPage)).mode).toBe("overview");
    },
  );

  test(
    "W6: the visible Help control replays the walk from either surface",
    { tag: ["@desktop", "@mobile"] },
    async ({ crawlPage }) => {
      for (const mode of ["overview", "workbench"] as const) {
        await crawlPage.goto(`/?mode=${mode}`);
        const help = crawlPage.locator('[data-testid="help-button"]:visible');
        await expect(help).toBeVisible({ timeout: 30_000 });
        await expect(help).toHaveText(/Help/);
        await help.click();
        const replay = crawlPage.locator('[data-testid="orientation-replay"]');
        await expect(replay).toBeVisible();
        await expect(replay).toHaveText("Replay guided tour");
        await replay.click();
        await waitForStop(crawlPage, "what-this-is");
        expect((await readNavState(crawlPage)).mode).toBe("overview");
        await crawlPage.locator('[data-testid="orientation-exit"]').click();
        await expect(crawlPage.locator('[data-testid="orientation-walk"]')).toHaveCount(0);
      }
    },
  );
});
