import { createServer } from "node:http";
import { mkdtempSync, readFileSync, existsSync, statSync } from "node:fs";
import { join, extname } from "node:path";
import { tmpdir } from "node:os";
import { exec } from "node:child_process";
import pc from "picocolors";
import { detectPython, runAnalyzer } from "../lib/python.js";
import { assembleStaticSite } from "../lib/viewer.js";

const MIME_TYPES: Record<string, string> = {
  ".html": "text/html",
  ".js": "application/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

export interface ServeOptions {
  repoPath: string;
  port: number;
  open: boolean;
  compact?: boolean;
  pretty?: boolean;
  config?: string;
}

export async function serve(options: ServeOptions): Promise<void> {
  console.log();
  console.log(pc.bold("SysCorpus"));
  console.log();

  // Step 1: Detect Python
  console.log(`${pc.green("1.")} Checking Python...`);
  const python = await detectPython();
  console.log(pc.dim(`  Found: ${python}`));

  // Step 2: Run analyzer in split mode (uncapped: no silent symbol truncation).
  console.log(`${pc.green("2.")} Analyzing codebase...`);
  const siteDir = mkdtempSync(join(tmpdir(), "solution-explorer-"));
  const archDir = join(siteDir, "arch-output");

  await runAnalyzer(python, {
    repoPath: options.repoPath,
    outputPath: archDir,
    compact: options.compact,
    pretty: options.pretty,
    config: options.config,
    split: true,
  });

  console.log(pc.dim("  Analysis complete."));

  // Step 3: Assemble site
  console.log(`${pc.green("3.")} Assembling viewer...`);
  assembleStaticSite(siteDir, archDir, { split: true });

  // Step 4: Serve
  const server = createServer((req, res) => {
    let filePath = join(siteDir, req.url === "/" ? "/index.html" : req.url!);

    // SPA fallback: if the file doesn't exist and isn't a static asset, serve index.html
    if (!existsSync(filePath) || !statSync(filePath).isFile()) {
      filePath = join(siteDir, "index.html");
    }

    try {
      const content = readFileSync(filePath);
      const ext = extname(filePath);
      res.writeHead(200, {
        "Content-Type": MIME_TYPES[ext] || "application/octet-stream",
        "Cache-Control": "no-cache",
      });
      res.end(content);
    } catch {
      res.writeHead(404);
      res.end("Not found");
    }
  });

  server.listen(options.port, () => {
    const url = `http://localhost:${options.port}`;
    console.log();
    console.log(
      pc.green("Ready!"),
      `Serving at ${pc.bold(pc.cyan(url))}`
    );
    console.log(pc.dim("Press Ctrl+C to stop."));
    console.log();

    if (options.open) {
      openBrowser(url);
    }
  });

  // Graceful shutdown
  process.on("SIGINT", () => {
    console.log(pc.dim("\nShutting down..."));
    server.close();
    process.exit(0);
  });
}

function openBrowser(url: string): void {
  const cmd =
    process.platform === "darwin"
      ? "open"
      : process.platform === "win32"
        ? "start"
        : "xdg-open";

  exec(`${cmd} ${url}`, () => {
    // Ignore errors (e.g., no display server in CI)
  });
}
