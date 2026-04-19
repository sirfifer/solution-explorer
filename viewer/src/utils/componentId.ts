// Must stay in sync with safe_component_id() in analyzer/cli.py.
// Escapes characters forbidden by GitHub's actions/upload-artifact (NTFS-incompatible)
// so per-component detail filenames survive artifact upload and download.
export function safeComponentId(id: string): string {
  return id.replace(/\//g, "--").replace(/:/g, "__");
}
