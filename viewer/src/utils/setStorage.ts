/**
 * Persistence for selection sets and set-level annotations (P6-9).
 *
 * Sets and their annotations are review output, like single-element annotations,
 * so they must survive a hard reload and re-analysis. This module mirrors
 * annotationStorage.ts exactly: a single localStorage key holding data for every
 * architecture identity, keyed by the STABLE `architectureIdentity` (name plus
 * repository, never `generated_at`), a schema version that drops mismatched
 * payloads rather than misreading them, a size guard, and swallowed quota
 * failures so a write never crashes the app.
 */
import type { SelectionSet, SetAnnotation } from "../types";

// Re-export the shared identity helper so callers key sets the same way they key
// annotations, guaranteeing the two stores stay aligned per architecture.
export { architectureIdentity } from "./annotationStorage";

// Single localStorage key holding selection sets for every architecture identity.
const STORAGE_KEY = "arch-selection-sets";
// Schema version. Bump when the stored shape changes; mismatched payloads are
// dropped rather than misread.
const SCHEMA_VERSION = 1;
// Size guard, consistent with annotationStorage.ts: do not attempt to persist an
// unreasonably large payload.
const MAX_BYTES = 2_000_000;

export interface SetBundle {
  sets: SelectionSet[];
  annotations: SetAnnotation[];
}

interface SetStoreShape {
  version: number;
  byArch: Record<string, SetBundle>;
}

function emptyBundle(): SetBundle {
  return { sets: [], annotations: [] };
}

function readStore(): SetStoreShape {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { version: SCHEMA_VERSION, byArch: {} };
    const parsed = JSON.parse(raw);
    if (
      parsed &&
      parsed.version === SCHEMA_VERSION &&
      parsed.byArch &&
      typeof parsed.byArch === "object"
    ) {
      return parsed as SetStoreShape;
    }
    // Unknown or older schema: drop it rather than render stale/incompatible data.
    return { version: SCHEMA_VERSION, byArch: {} };
  } catch {
    // Corrupt JSON or storage unavailable.
    return { version: SCHEMA_VERSION, byArch: {} };
  }
}

/** Load persisted sets and set-annotations for the given architecture identity. */
export function loadSelectionSets(identity: string): SetBundle {
  const store = readStore();
  const bundle = store.byArch[identity];
  if (!bundle) return emptyBundle();
  return {
    sets: Array.isArray(bundle.sets) ? bundle.sets : [],
    annotations: Array.isArray(bundle.annotations) ? bundle.annotations : [],
  };
}

/**
 * Persist sets and set-annotations for the given architecture identity. A quota
 * failure or missing storage is swallowed so the app never crashes on a write,
 * matching annotationStorage.ts and the other localStorage writers in the store.
 */
export function saveSelectionSets(
  identity: string,
  sets: SelectionSet[],
  annotations: SetAnnotation[],
): void {
  try {
    const store = readStore();
    if (sets.length === 0 && annotations.length === 0) {
      delete store.byArch[identity];
    } else {
      store.byArch[identity] = { sets, annotations };
    }
    const serialized = JSON.stringify(store);
    if (serialized.length > MAX_BYTES) {
      console.warn(
        `[selection-sets] Not persisting: payload ${serialized.length} bytes exceeds ${MAX_BYTES} byte limit.`,
      );
      return;
    }
    localStorage.setItem(STORAGE_KEY, serialized);
  } catch {
    // Quota exceeded or storage unavailable: keep sets in memory only.
  }
}
