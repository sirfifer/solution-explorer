export interface LiveMonitorOptions {
    liveMode: "github" | "cloudflare";
}
export declare function liveMonitorWorkflow(options: LiveMonitorOptions): string;
