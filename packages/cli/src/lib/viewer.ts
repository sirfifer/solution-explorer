import { existsSync, cpSync, copyFileSync, mkdirSync, rmSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

/** Find the bundled pre-built viewer directory. */
export function getViewerDistPath(): string {
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

  throw new Error(
    "Could not find the pre-built viewer. Run `npm run build` in the viewer/ directory first."
  );
}

export interface AssembleOptions {
  /**
   * When true, `architectureSource` is a split-output directory (manifest.json +
   * data/) and is copied to `<outputDir>/architecture`, which the viewer
   * auto-detects. When false, it is a single architecture.json file.
   */
  split?: boolean;
}

/**
 * Copy the pre-built viewer and the analyzer output to an output directory.
 *
 * In split mode `architectureSource` is a directory; in single-file mode it is
 * the path to architecture.json.
 */
export function assembleStaticSite(
  outputDir: string,
  architectureSource: string,
  options: AssembleOptions = {}
): void {
  const viewerDist = getViewerDistPath();

  // Create output directory
  mkdirSync(outputDir, { recursive: true });

  // Copy the entire viewer dist
  cpSync(viewerDist, outputDir, { recursive: true });

  if (options.split) {
    // Split output: replace any bundled sample dataset with the fresh scan.
    // Removing the stale monolith too keeps the manifest authoritative.
    const archDir = join(outputDir, "architecture");
    rmSync(archDir, { recursive: true, force: true });
    rmSync(join(outputDir, "architecture.json"), { force: true });
    cpSync(architectureSource, archDir, { recursive: true });
  } else {
    // Single-file output: copy the architecture JSON into the output
    copyFileSync(architectureSource, join(outputDir, "architecture.json"));
  }
}
