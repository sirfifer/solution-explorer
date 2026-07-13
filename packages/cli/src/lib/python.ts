import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import pc from "picocolors";

const execFileAsync = promisify(execFile);

const __dirname = dirname(fileURLToPath(import.meta.url));

/** Find the bundled analyzer directory (shipped with the npm package). */
export function getAnalyzerPath(): string {
  // When installed via npm, the analyzer is bundled at the package root
  const packageRoot = join(__dirname, "..", "..");
  const bundled = join(packageRoot, "analyze.py");
  if (existsSync(bundled)) {
    return packageRoot;
  }

  // Development: analyzer is at the repo root
  const repoRoot = join(packageRoot, "..", "..");
  const dev = join(repoRoot, "analyze.py");
  if (existsSync(dev)) {
    return repoRoot;
  }

  throw new Error(
    "Could not find the analyzer. If running from source, make sure you're in the solution-explorer repo."
  );
}

/** Detect a usable Python 3.10+ binary. */
export async function detectPython(): Promise<string> {
  const candidates = ["python3", "python"];

  for (const cmd of candidates) {
    try {
      const { stdout } = await execFileAsync(cmd, [
        "-c",
        "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
      ]);
      const version = stdout.trim();
      const [major, minor] = version.split(".").map(Number);
      if (major === 3 && minor >= 10) {
        return cmd;
      }
    } catch {
      // Not found or wrong version, try next
    }
  }

  console.error(pc.red("Python 3.10+ is required but was not found."));
  console.error();
  console.error("Install Python from https://www.python.org/downloads/");
  console.error("or via your package manager:");
  console.error(`  ${pc.cyan("brew install python3")}        (macOS)`);
  console.error(`  ${pc.cyan("sudo apt install python3")}    (Ubuntu/Debian)`);
  console.error(`  ${pc.cyan("winget install Python.Python.3.12")}  (Windows)`);
  process.exit(1);
}

export interface AnalyzeOptions {
  repoPath: string;
  outputPath: string;
  compact?: boolean;
  pretty?: boolean;
  config?: string;
  /**
   * Emit split output (manifest.json + per-component detail files) instead of a
   * single architecture.json. Split mode runs uncapped, so no symbols are
   * silently truncated (F-AN-3). The viewer auto-detects the manifest.
   */
  split?: boolean;
}

/**
 * Build the argument vector passed to analyze.py.
 *
 * Extracted so the command can be asserted in a unit test without spawning
 * Python. The default CLI paths pass `split: true` for uncapped output.
 */
export function buildAnalyzerArgs(
  analyzeScript: string,
  options: AnalyzeOptions
): string[] {
  const args: string[] = [analyzeScript];

  if (options.config) {
    args.push("--config", options.config);
  } else {
    args.push(options.repoPath);
  }

  args.push("-o", options.outputPath);

  if (options.split) {
    args.push("--split");
  }

  // Compact by default: smaller JSON for hosted static sites, in both modes.
  // An explicit --pretty wins, since the analyzer treats --compact as an
  // override that would otherwise make the user's flag a silent no-op.
  if (options.pretty) {
    args.push("--pretty");
  } else {
    args.push("--compact");
  }

  return args;
}

/** Run the Python analyzer against a repository. */
export async function runAnalyzer(
  python: string,
  options: AnalyzeOptions
): Promise<void> {
  const analyzerRoot = getAnalyzerPath();
  const analyzeScript = join(analyzerRoot, "analyze.py");

  const args = buildAnalyzerArgs(analyzeScript, options);

  console.log(
    pc.dim(`  Running analyzer on ${options.config || options.repoPath}...`)
  );

  try {
    const { stderr } = await execFileAsync(python, args, {
      maxBuffer: 50 * 1024 * 1024, // 50MB for large codebases
      timeout: 300_000, // 5 minutes
    });
    if (stderr) {
      // Analyzer may print warnings to stderr
      for (const line of stderr.split("\n").filter(Boolean)) {
        console.log(pc.yellow(`  ${line}`));
      }
    }
  } catch (err: unknown) {
    const error = err as Error & { stderr?: string };
    throw new Error(
      `Analyzer failed: ${error.stderr || error.message}`
    );
  }
}
