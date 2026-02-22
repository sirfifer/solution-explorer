/** Find the bundled pre-built viewer directory. */
export declare function getViewerDistPath(): string;
/** Copy the pre-built viewer and architecture.json to an output directory. */
export declare function assembleStaticSite(outputDir: string, architectureJsonPath: string): void;
