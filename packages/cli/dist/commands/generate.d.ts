export interface GenerateOptions {
    repoPath: string;
    outputDir: string;
    compact?: boolean;
    pretty?: boolean;
    config?: string;
}
export declare function generate(options: GenerateOptions): Promise<void>;
