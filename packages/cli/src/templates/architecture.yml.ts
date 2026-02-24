export interface WorkflowOptions {
  branches: string[];
  deployTo: "github-pages" | "cloudflare" | "artifact-only";
  cloudflareProjectName?: string;
}

export function architectureWorkflow(options: WorkflowOptions): string {
  const branchList = options.branches.map((b) => `'${b}'`).join(", ");

  const cloudflareInputs =
    options.deployTo === "cloudflare"
      ? `
          deploy-to: cloudflare
          cloudflare-api-token: \${{ secrets.CLOUDFLARE_API_TOKEN }}
          cloudflare-account-id: \${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          cloudflare-project-name: '${options.cloudflareProjectName || "solution-explorer"}'`
      : options.deployTo === "github-pages"
        ? `
          deploy-to: github-pages`
        : "";

  const permissions =
    options.deployTo === "github-pages"
      ? `
permissions:
  contents: read
  pages: write
  id-token: write`
      : `
permissions:
  contents: read`;

  const environment =
    options.deployTo === "github-pages"
      ? `
    environment:
      name: github-pages
      url: \${{ steps.deploy.outputs.page_url }}`
      : "";

  const deployStep =
    options.deployTo === "github-pages"
      ? `

      - name: Deploy to GitHub Pages
        id: deploy
        uses: actions/deploy-pages@v4`
      : "";

  return `name: Architecture Visualization

on:
  push:
    branches: [${branchList}]
  pull_request:
    branches: [${branchList}]
  workflow_dispatch:

concurrency:
  group: architecture-\${{ github.ref }}
  cancel-in-progress: true
${permissions}

jobs:
  visualize:
    name: Generate & Deploy Architecture Viz
    runs-on: ubuntu-latest${environment}
    steps:
      - uses: actions/checkout@v4

      - uses: sirfifer/solution-explorer@latest
        with:
          config: solution-explorer.json${cloudflareInputs}${deployStep}
`;
}
