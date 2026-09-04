import { cp, mkdir, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

// A disposable test artifact; only viewer assets and the synthetic projection
// are copied. No canonical store or private demo dataset is needed in CI.
const here = path.dirname(fileURLToPath(import.meta.url));
const dist = path.resolve(here, "../../dist");
const output = path.join(here, "results/reading-fixture");
await mkdir(path.join(output, "architecture"), { recursive: true });
for (const entry of await readdir(dist, { withFileTypes: true })) {
  if (["architecture", "architecture.json", "ai.json", "llms.txt"].includes(entry.name)) continue;
  await cp(path.join(dist, entry.name), path.join(output, entry.name), { recursive: true });
}
await cp(path.join(here, "fixtures/reading/manifest.json"), path.join(output, "architecture/manifest.json"));
