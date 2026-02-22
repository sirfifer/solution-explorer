import { existsSync, cpSync, copyFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
const __dirname = dirname(fileURLToPath(import.meta.url));
/** Find the bundled pre-built viewer directory. */
export function getViewerDistPath() {
    // When installed via npm, viewer-dist is at the package root
    const packageRoot = join(__dirname, "..", "..");
    const bundled = join(packageRoot, "viewer-dist");
    if (existsSync(bundled)) {
        return bundled;
    }
    // Development: use the viewer's built output
    const repoRoot = join(packageRoot, "..", "..");
    const dev = join(repoRoot, "viewer", "dist");
    if (existsSync(dev)) {
        return dev;
    }
    throw new Error("Could not find the pre-built viewer. Run `npm run build` in the viewer/ directory first.");
}
/** Copy the pre-built viewer and architecture.json to an output directory. */
export function assembleStaticSite(outputDir, architectureJsonPath) {
    const viewerDist = getViewerDistPath();
    // Create output directory
    mkdirSync(outputDir, { recursive: true });
    // Copy the entire viewer dist
    cpSync(viewerDist, outputDir, { recursive: true });
    // Copy the architecture JSON into the output
    copyFileSync(architectureJsonPath, join(outputDir, "architecture.json"));
}
