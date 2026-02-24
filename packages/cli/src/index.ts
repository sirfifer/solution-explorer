#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { parseArgs } from "node:util";
import { fileURLToPath } from "node:url";
import pc from "picocolors";
import { generate } from "./commands/generate.js";
import { serve } from "./commands/serve.js";
import { init } from "./commands/init.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const VERSION = JSON.parse(
  readFileSync(join(__dirname, "..", "package.json"), "utf-8"),
).version;

const HELP = `
${pc.bold("solution-explorer")} - Generate interactive architecture diagrams from any codebase

${pc.bold("Usage:")}
  ${pc.cyan("npx solution-explorer")} [path]              Analyze and serve locally
  ${pc.cyan("npx solution-explorer")} --out <dir> [path]  Export static site to directory
  ${pc.cyan("npx solution-explorer init")}                 Set up GitHub Actions workflow
  ${pc.cyan("npx solution-explorer init --live")}          Set up full live monitoring

${pc.bold("Options:")}
  --out, -o <dir>   Export static files to directory instead of serving
  --port, -p <n>    Port for local server (default: 3000)
  --no-open         Don't open browser automatically
  --live            Include live monitoring setup (with init)
  --help, -h        Show this help
  --version, -v     Show version

${pc.bold("Examples:")}
  ${pc.dim("# Analyze current directory and open in browser")}
  npx solution-explorer

  ${pc.dim("# Analyze a specific repo and export static files")}
  npx solution-explorer --out ./docs/architecture /path/to/repo

  ${pc.dim("# Set up automated GitHub Actions workflow")}
  npx solution-explorer init

  ${pc.dim("# Set up with live monitoring")}
  npx solution-explorer init --live

${pc.bold("Prerequisites:")}
  Python 3.10+  (for code analysis)
  Node.js 20+   (for this CLI)
`;

async function main() {
  const { values, positionals } = parseArgs({
    allowPositionals: true,
    options: {
      out: { type: "string", short: "o" },
      port: { type: "string", short: "p", default: "3000" },
      open: { type: "boolean", default: true },
      live: { type: "boolean", default: false },
      help: { type: "boolean", short: "h", default: false },
      version: { type: "boolean", short: "v", default: false },
      compact: { type: "boolean", default: false },
      pretty: { type: "boolean", default: false },
      config: { type: "string" },
    },
  });

  if (values.version) {
    console.log(VERSION);
    process.exit(0);
  }

  if (values.help) {
    console.log(HELP);
    process.exit(0);
  }

  const command = positionals[0];

  if (command === "init") {
    await init({ live: values.live ?? false });
    return;
  }

  // Default command: generate (and optionally serve)
  const repoPath = command || ".";
  const port = parseInt(values.port ?? "3000", 10);

  if (values.out) {
    await generate({
      repoPath,
      outputDir: values.out,
      compact: values.compact,
      pretty: values.pretty,
      config: values.config,
    });
  } else {
    await serve({
      repoPath,
      port,
      open: values.open ?? true,
      compact: values.compact,
      pretty: values.pretty,
      config: values.config,
    });
  }
}

main().catch((err) => {
  console.error(pc.red("Error:"), err.message);
  process.exit(1);
});
