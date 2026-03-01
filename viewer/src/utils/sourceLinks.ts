import type { Architecture } from "../types";

export interface SourceLinkInfo {
  url: string;
  repoName?: string;
}

/**
 * Build a GitHub URL for a file path, optionally with line number(s).
 * Handles both single-repo and multi-repo architectures.
 * Returns null if no repository URL is configured.
 */
export function getSourceUrl(
  architecture: Architecture,
  filePath: string,
  line?: number,
  endLine?: number,
): SourceLinkInfo | null {
  // Multi-repo: file paths are prefixed with "repoName/"
  if (architecture.repositories && architecture.repositories.length > 1) {
    for (const repo of architecture.repositories) {
      const prefix = `${repo.name}/`;
      if (filePath.startsWith(prefix)) {
        const repoUrl = repo.repository;
        if (!repoUrl) return null;
        const branch = repo.default_branch || architecture.default_branch || "main";
        const relativePath = filePath.slice(prefix.length);
        let url = `${repoUrl.replace(/\/$/, "")}/blob/${branch}/${relativePath}`;
        if (line) url += `#L${line}`;
        if (endLine && endLine !== line) url += `-L${endLine}`;
        return { url, repoName: repo.name };
      }
    }
    return null;
  }

  // Single repo
  const repoUrl = architecture.repository;
  if (!repoUrl) return null;
  const branch = architecture.default_branch || "main";
  let url = `${repoUrl.replace(/\/$/, "")}/blob/${branch}/${filePath}`;
  if (line) url += `#L${line}`;
  if (endLine && endLine !== line) url += `-L${endLine}`;
  return { url };
}
