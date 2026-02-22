export interface WorkflowOptions {
    branches: string[];
    deployTo: "github-pages" | "cloudflare" | "artifact-only";
    cloudflareProjectName?: string;
}
export declare function architectureWorkflow(options: WorkflowOptions): string;
