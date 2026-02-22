export interface ConfigOptions {
  name: string;
  description: string;
  repoName: string;
}

export function solutionExplorerConfig(options: ConfigOptions): string {
  return JSON.stringify(
    {
      solution: options.name,
      description: options.description,
      repositories: [{ name: options.repoName, path: "." }],
    },
    null,
    2
  );
}
