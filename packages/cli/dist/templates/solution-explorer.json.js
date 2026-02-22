export function solutionExplorerConfig(options) {
    return JSON.stringify({
        solution: options.name,
        description: options.description,
        repositories: [{ name: options.repoName, path: "." }],
    }, null, 2);
}
