import { existsSync, writeFileSync, mkdirSync, cpSync } from "node:fs";
import { join, dirname } from "node:path";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import prompts from "prompts";
import pc from "picocolors";
import {
  architectureWorkflow,
  type WorkflowOptions,
} from "../templates/architecture.yml.js";
import {
  liveMonitorWorkflow,
  type LiveMonitorOptions,
} from "../templates/live-monitor.yml.js";
import { solutionExplorerConfig } from "../templates/solution-explorer.json.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

export interface InitOptions {
  live: boolean;
}

export async function init(options: InitOptions): Promise<void> {
  console.log();
  console.log(pc.bold("SysCorpus Setup"));
  if (options.live) {
    console.log(pc.dim("Mode: Full live monitoring"));
  } else {
    console.log(pc.dim("Mode: Automated workflow"));
  }
  console.log();

  // Check if we're in a git repo
  if (!existsSync(".git")) {
    console.error(
      pc.red("This directory is not a git repository."),
      "Run this from your project root."
    );
    process.exit(1);
  }

  // Gather repo info
  const repoInfo = getRepoInfo();

  // Check for existing files
  const hasConfig = existsSync("solution-explorer.json");
  const hasWorkflow = existsSync(".github/workflows/architecture.yml");

  if (hasConfig || hasWorkflow) {
    const { overwrite } = await prompts({
      type: "confirm",
      name: "overwrite",
      message: `Found existing ${hasConfig ? "solution-explorer.json" : ""}${hasConfig && hasWorkflow ? " and " : ""}${hasWorkflow ? ".github/workflows/architecture.yml" : ""}. Overwrite?`,
      initial: false,
    });

    if (!overwrite) {
      console.log(pc.dim("Cancelled."));
      return;
    }
  }

  // Interactive prompts
  const answers = await prompts([
    {
      type: "text",
      name: "name",
      message: "Project name?",
      initial: repoInfo.name || basename(process.cwd()),
    },
    {
      type: "text",
      name: "description",
      message: "Description?",
      initial: repoInfo.description || "",
    },
    {
      type: "select",
      name: "deployTo",
      message: "Where should the visualization be deployed?",
      choices: [
        {
          title: "GitHub Pages",
          value: "github-pages",
          description: "Free, automatic. Served from your repo's GitHub Pages.",
        },
        {
          title: "Cloudflare Pages",
          value: "cloudflare",
          description: "Fast global CDN. Requires Cloudflare account.",
        },
        {
          title: "Artifacts only",
          value: "artifact-only",
          description:
            "Download from GitHub Actions. No hosting setup needed.",
        },
      ],
    },
    {
      type: (prev) => (prev === "cloudflare" ? "text" : null),
      name: "cloudflareProjectName",
      message: "Cloudflare Pages project name?",
      initial: `${repoInfo.repoName || "my-project"}-architecture`,
    },
    {
      type: "multiselect",
      name: "branches",
      message: "Trigger on push to which branches?",
      choices: [
        { title: "main", value: "main", selected: true },
        { title: "develop", value: "develop" },
        { title: "master", value: "master" },
      ],
      min: 1,
    },
  ]);

  if (!answers.name || !answers.deployTo || !answers.branches) {
    console.log(pc.dim("Cancelled."));
    return;
  }

  // Live monitoring prompts
  let liveMode: "github" | "cloudflare" = "github";
  if (options.live) {
    const liveAnswers = await prompts({
      type: "select",
      name: "liveMode",
      message: "Live monitoring backend?",
      choices: [
        {
          title: "GitHub Pages",
          value: "github",
          description:
            "Free. Live data served from GitHub Pages with ~10 min cache.",
        },
        {
          title: "Cloudflare (enhanced)",
          value: "cloudflare",
          description:
            "Real-time updates via Worker + R2. Requires Cloudflare infrastructure.",
        },
      ],
    });

    if (!liveAnswers.liveMode) {
      console.log(pc.dim("Cancelled."));
      return;
    }
    liveMode = liveAnswers.liveMode;
  }

  console.log();
  console.log(pc.bold("Creating files..."));
  console.log();

  // Create solution-explorer.json
  const configContent = solutionExplorerConfig({
    name: answers.name,
    description: answers.description,
    repoName: repoInfo.repoName || basename(process.cwd()),
  });
  writeFileSync("solution-explorer.json", configContent + "\n");
  console.log(pc.green("  Created"), "solution-explorer.json");

  // Create architecture workflow
  const workflowOpts: WorkflowOptions = {
    branches: answers.branches,
    deployTo: answers.deployTo,
    cloudflareProjectName: answers.cloudflareProjectName,
  };
  const workflowContent = architectureWorkflow(workflowOpts);
  mkdirSync(".github/workflows", { recursive: true });
  writeFileSync(".github/workflows/architecture.yml", workflowContent);
  console.log(pc.green("  Created"), ".github/workflows/architecture.yml");

  // Live monitoring setup
  if (options.live) {
    const liveOpts: LiveMonitorOptions = { liveMode };
    const liveContent = liveMonitorWorkflow(liveOpts);
    writeFileSync(".github/workflows/live-monitor.yml", liveContent);
    console.log(pc.green("  Created"), ".github/workflows/live-monitor.yml");

    // Copy support scripts
    copyScripts();

    // Enable GitHub Pages
    if (hasGhCli()) {
      console.log();
      console.log(pc.dim("Enabling GitHub Pages..."));
      try {
        execSync(
          `gh api repos/${repoInfo.owner}/${repoInfo.repoName}/pages -X POST --input - <<< '{"build_type":"workflow"}' 2>/dev/null`,
          { stdio: "pipe" }
        );
        console.log(pc.green("  GitHub Pages enabled."));
      } catch {
        console.log(
          pc.yellow("  Could not auto-enable GitHub Pages."),
          "Enable manually: Settings > Pages > Source: GitHub Actions"
        );
      }
    }
  }

  // Post-setup instructions
  console.log();
  console.log(pc.green(pc.bold("Setup complete!")));
  console.log();

  if (answers.deployTo === "cloudflare") {
    console.log(pc.bold("Next steps:"));
    console.log(
      `  1. Set GitHub secrets: ${pc.cyan("CLOUDFLARE_API_TOKEN")} and ${pc.cyan("CLOUDFLARE_ACCOUNT_ID")}`
    );
    console.log("  2. Commit and push these files");
    console.log("  3. The workflow will run automatically");
    console.log();
  } else if (answers.deployTo === "github-pages") {
    console.log(pc.bold("Next steps:"));
    console.log(
      "  1. Enable GitHub Pages: Settings > Pages > Source: GitHub Actions"
    );
    console.log("  2. Commit and push these files");
    console.log("  3. The workflow will run automatically");
    console.log();
  } else {
    console.log(pc.bold("Next steps:"));
    console.log("  1. Commit and push these files");
    console.log(
      "  2. Download the visualization from the Actions artifact"
    );
    console.log();
  }

  if (options.live && liveMode === "cloudflare") {
    console.log(pc.bold("Cloudflare live monitoring setup:"));
    console.log("  Set these additional secrets on your repo:");
    console.log(`    ${pc.cyan("CF_WORKER_URL")}          Your Worker URL`);
    console.log(`    ${pc.cyan("CF_INGEST_TOKEN")}        Worker ingest token`);
    console.log(
      `    ${pc.cyan("CF_R2_ACCESS_KEY_ID")}    R2 access key`
    );
    console.log(
      `    ${pc.cyan("CF_R2_SECRET_ACCESS_KEY")} R2 secret key`
    );
    console.log(`    ${pc.cyan("CF_R2_ENDPOINT")}         R2 endpoint URL`);
    console.log();
    console.log(
      pc.dim("Deploy the Worker first if you haven't:"),
    );
    console.log(
      pc.dim("  git clone https://github.com/sirfifer/solution-explorer.git")
    );
    console.log(
      pc.dim("  cd solution-explorer/infrastructure/cloudflare && bash setup.sh")
    );
    console.log();
  }

  // Show what files to commit
  console.log(pc.bold("Files to commit:"));
  console.log("  solution-explorer.json");
  console.log("  .github/workflows/architecture.yml");
  if (options.live) {
    console.log("  .github/workflows/live-monitor.yml");
    console.log("  scripts/collect-ci-status.py");
    console.log("  scripts/generate-admin-summary.py");
  }
  console.log();
}

interface RepoInfo {
  owner: string;
  repoName: string;
  name: string;
  description: string;
}

function getRepoInfo(): RepoInfo {
  const info: RepoInfo = {
    owner: "",
    repoName: "",
    name: "",
    description: "",
  };

  if (!hasGhCli()) {
    return info;
  }

  try {
    const output = execSync(
      "gh repo view --json nameWithOwner,description 2>/dev/null",
      { encoding: "utf-8", stdio: ["pipe", "pipe", "pipe"] }
    );
    const data = JSON.parse(output);
    if (data.nameWithOwner) {
      const [owner, repoName] = data.nameWithOwner.split("/");
      info.owner = owner;
      info.repoName = repoName;
      info.name = repoName;
    }
    if (data.description) {
      info.description = data.description;
    }
  } catch {
    // gh CLI not available or not in a GitHub repo
  }

  return info;
}

function hasGhCli(): boolean {
  try {
    execSync("which gh", { stdio: "pipe" });
    return true;
  } catch {
    return false;
  }
}

function copyScripts(): void {
  // Find the bundled scripts directory
  const packageRoot = join(__dirname, "..", "..");
  const candidates = [
    join(packageRoot, "scripts-bundle"), // npm installed
    join(packageRoot, "..", "..", "scripts"), // development
  ];

  let scriptsDir: string | null = null;
  for (const dir of candidates) {
    if (existsSync(join(dir, "collect-ci-status.py"))) {
      scriptsDir = dir;
      break;
    }
  }

  if (!scriptsDir) {
    console.log(
      pc.yellow("  Could not find bundled scripts."),
      "Copy them manually from the solution-explorer repo."
    );
    return;
  }

  mkdirSync("scripts", { recursive: true });

  const files = ["collect-ci-status.py", "generate-admin-summary.py"];
  for (const file of files) {
    const src = join(scriptsDir, file);
    if (existsSync(src)) {
      cpSync(src, join("scripts", file));
      console.log(pc.green("  Copied"), `scripts/${file}`);
    }
  }
}

function basename(p: string): string {
  return p.split("/").pop() || p;
}
