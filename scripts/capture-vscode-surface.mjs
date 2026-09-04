#!/usr/bin/env node
/** Capture a sanitized VS Code workbench and its source-linked regions.
 *
 * Usage: node scripts/capture-vscode-surface.mjs <code-executable> <workspace> <output-dir>
 * The output is deliberately raw (capture.png + regions.json). Packaging adds
 * analyzed-subject provenance and code evidence separately.
 */
import playwright from "../viewer/node_modules/playwright-core/index.js";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";

const [executablePath, workspacePath, outputPath] = process.argv.slice(2);
const { _electron: electron } = playwright;
if (!executablePath || !workspacePath || !outputPath) {
  throw new Error("expected <code-executable> <workspace> <output-dir>");
}

await mkdir(outputPath, { recursive: true });
// VS Code's macOS IPC socket has a hard 103-character path limit. Keep the
// disposable profile in the system temp directory even when artifacts have a
// long, descriptive destination.
const sessionPath = await mkdtemp(path.join(tmpdir(), "syscorpus-code-"));
const userDataPath = path.join(sessionPath, "profile");
const extensionsPath = path.join(sessionPath, "extensions");
await mkdir(extensionsPath, { recursive: true });
await mkdir(path.join(userDataPath, "User"), { recursive: true });
await writeFile(
  path.join(userDataPath, "User", "settings.json"),
  `${JSON.stringify({ "extensions.ignoreRecommendations": true }, null, 2)}\n`,
);

const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
let app;
try {
  app = await electron.launch({
    executablePath,
    env,
    args: [
      workspacePath,
      path.join(workspacePath, "src/vs/workbench/browser/parts/editor/editorPart.ts"),
      "--user-data-dir", userDataPath,
      "--extensions-dir", extensionsPath,
      "--disable-telemetry",
      "--disable-workspace-trust",
      "--skip-welcome",
      "--skip-release-notes",
      "--new-window",
      "--window-size=1440,900",
    ],
    timeout: 60_000,
  });
  const window = await app.firstWindow({ timeout: 60_000 });
  await window.waitForSelector(".monaco-workbench", { timeout: 60_000 });
  await window.waitForTimeout(8_000);

  const selectors = {
    "activity-bar": "#workbench\\.parts\\.activitybar",
    "side-bar": "#workbench\\.parts\\.sidebar",
    editor: "#workbench\\.parts\\.editor",
    panel: "#workbench\\.parts\\.panel",
    "status-bar": "#workbench\\.parts\\.statusbar",
    "title-bar": "#workbench\\.parts\\.titlebar",
    "auxiliary-bar": "#workbench\\.parts\\.auxiliarybar",
  };
  const viewport = await window.evaluate(() => ({ width: innerWidth, height: innerHeight }));
  const regions = {};
  for (const [id, selector] of Object.entries(selectors)) {
    const locator = window.locator(selector).first();
    if (await locator.count()) {
      const box = await locator.boundingBox();
      if (box && box.width > 0 && box.height > 0) regions[id] = box;
    }
  }
  await window.screenshot({ path: path.join(outputPath, "capture.png") });
  await writeFile(path.join(outputPath, "regions.json"), `${JSON.stringify({ viewport, regions }, null, 2)}\n`);
} finally {
  if (app) await app.close();
  await rm(sessionPath, { recursive: true, force: true });
}
