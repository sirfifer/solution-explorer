// Must stay in sync with safe_component_id() in analyzer/cli.py and
// safeComponentId() in viewer/src/utils/componentId.ts.
// Escapes characters forbidden by GitHub's actions/upload-artifact
// (NTFS-incompatible) so per-component detail filenames survive artifact
// upload and download. If these three implementations drift, the worker's
// cleanupOrphanedDetails will delete freshly uploaded detail files (F-CRIT-5).
export function safeComponentId(id: string): string {
  return id.replace(/\//g, "--").replace(/:/g, "__");
}
