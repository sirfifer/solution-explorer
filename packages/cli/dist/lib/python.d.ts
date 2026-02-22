/** Find the bundled analyzer directory (shipped with the npm package). */
export declare function getAnalyzerPath(): string;
/** Detect a usable Python 3.10+ binary. */
export declare function detectPython(): Promise<string>;
export interface AnalyzeOptions {
    repoPath: string;
    outputPath: string;
    compact?: boolean;
    pretty?: boolean;
    config?: string;
}
/** Run the Python analyzer against a repository. */
export declare function runAnalyzer(python: string, options: AnalyzeOptions): Promise<void>;
