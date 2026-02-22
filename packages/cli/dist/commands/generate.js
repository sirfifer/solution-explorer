import { mkdirSync, mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import pc from "picocolors";
import { detectPython, runAnalyzer } from "../lib/python.js";
import { assembleStaticSite } from "../lib/viewer.js";
export async function generate(options) {
    console.log();
    console.log(pc.bold("Solution Explorer"));
    console.log();
    // Step 1: Detect Python
    console.log(`${pc.green("1.")} Checking Python...`);
    const python = await detectPython();
    console.log(pc.dim(`  Found: ${python}`));
    // Step 2: Run analyzer
    console.log(`${pc.green("2.")} Analyzing codebase...`);
    const tmp = mkdtempSync(join(tmpdir(), "solution-explorer-"));
    const jsonPath = join(tmp, "architecture.json");
    await runAnalyzer(python, {
        repoPath: options.repoPath,
        outputPath: jsonPath,
        compact: options.compact,
        pretty: options.pretty,
        config: options.config,
    });
    console.log(pc.dim("  Analysis complete."));
    // Step 3: Assemble static site
    console.log(`${pc.green("3.")} Building static site...`);
    mkdirSync(options.outputDir, { recursive: true });
    assembleStaticSite(options.outputDir, jsonPath);
    console.log();
    console.log(pc.green("Done!"), `Static site written to ${pc.bold(options.outputDir)}`);
    console.log();
    console.log(pc.dim("You can serve these files with any static web server:"));
    console.log(pc.dim(`  npx serve ${options.outputDir}`));
    console.log(pc.dim(`  python3 -m http.server -d ${options.outputDir} 8000`));
    console.log();
}
