export interface ServeOptions {
    repoPath: string;
    port: number;
    open: boolean;
    compact?: boolean;
    pretty?: boolean;
    config?: string;
}
export declare function serve(options: ServeOptions): Promise<void>;
