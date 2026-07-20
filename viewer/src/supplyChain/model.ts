/**
 * Supply chain surface model helpers (P10-1).
 *
 * Pure, dataset-driven helpers the surface and its tests share: presence
 * detection, grouping dependencies by ecosystem (direct before transitive, then
 * name, as the projection already ranked them), pin-status labels, and the
 * dependency filter. No AI, no rendering; the deterministic skeleton stands on
 * its own (VISION.md).
 */
import type {
  Architecture,
  SupplyChain,
  SupplyChainDependency,
  SupplyChainEcosystem,
} from "../types";

/** Whether the dataset carries a supply chain section worth a surface. */
export function hasSupplyChain(arch: Architecture | null): boolean {
  const sc = arch?.supply_chain;
  if (!sc) return false;
  return (
    sc.dependencies.length > 0 ||
    sc.targets.length > 0 ||
    sc.warnings.length > 0 ||
    (sc.vendored?.length ?? 0) > 0
  );
}

/** The dependencies of one ecosystem, in the projection's ranked order. */
export function dependenciesForEcosystem(
  sc: SupplyChain,
  ecosystemId: string,
): SupplyChainDependency[] {
  return sc.dependencies.filter((d) => d.ecosystem === ecosystemId);
}

/** Filter a dependency list to direct only, transitive only, or all. */
export function filterByScope(
  deps: SupplyChainDependency[],
  scope: "all" | "direct" | "transitive",
): SupplyChainDependency[] {
  if (scope === "all") return deps;
  return deps.filter((d) => d.scope === scope);
}

/** A short, human label for a pin status. */
export function pinLabel(status: string): string {
  switch (status) {
    case "exact-pinned":
      return "pinned";
    case "range":
      return "range";
    case "unpinned":
      return "unpinned";
    default:
      return status;
  }
}

/** The ecosystem summary block for an id, when present. */
export function ecosystemSummary(
  sc: SupplyChain,
  ecosystemId: string,
): SupplyChainEcosystem | undefined {
  return sc.ecosystems.find((e) => e.id === ecosystemId);
}

/** An evidence label like "path/to/manifest:12" (line omitted when absent). */
export function evidenceLabel(evidence: { file: string; line?: number }): string {
  return evidence.line != null ? `${evidence.file}:${evidence.line}` : evidence.file;
}
