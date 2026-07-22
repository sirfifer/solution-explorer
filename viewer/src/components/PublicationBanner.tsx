// Publication header banner (always region). Renders publication.header.banner
// at the top of every page when a valid publication.json sidecar is present.
// Design authority: docs/publication/PUBLICATION-METADATA.md (placement rule 4:
// header content at the top, always region on every page and view).
//
// Pure presentation. When no valid publication is loaded this renders nothing, so
// the viewer is byte-identical to today (design rule 2). Fully functional at
// 390px: the text wraps, there is no horizontal scroll, and there are no
// hover-only affordances.

import { useArchStore } from "../store";
import { resolvePublicationText } from "../utils/publication";

export function PublicationBanner() {
  const publication = useArchStore((s) => s.publication);
  const darkMode = useArchStore((s) => s.darkMode);

  if (!publication) return null;

  const banner = resolvePublicationText(publication.header.banner, publication);
  if (!banner) return null;

  const isPrivatePreview = publication.access.visibility === "private-preview";

  return (
    <div
      role="note"
      data-testid="publication-banner"
      className={`
        shrink-0 px-4 py-1.5 text-xs leading-relaxed border-b
        ${isPrivatePreview
          ? (darkMode
              ? "bg-amber-950/40 border-amber-800/40 text-amber-200"
              : "bg-amber-50 border-amber-200 text-amber-800")
          : (darkMode
              ? "bg-zinc-900/60 border-zinc-800 text-zinc-300"
              : "bg-zinc-50 border-zinc-200 text-zinc-600")
        }
      `}
    >
      <p className="break-words">
        {isPrivatePreview && (
          <span className="font-semibold mr-1">Unpublished preview:</span>
        )}
        {banner}
      </p>
    </div>
  );
}
