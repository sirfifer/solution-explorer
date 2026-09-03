// Publication footer attribution (always region). Renders publication.footer.always
// at the bottom of every page when a valid publication.json sidecar is present.
// Design authority: docs/publication/PUBLICATION-METADATA.md (placement rule 4:
// footer content at the bottom, always region on every page; tool attribution is
// footer boilerplate and is always present).
//
// Pure presentation. When no valid publication is loaded this renders nothing, so
// the viewer is byte-identical to today (design rule 2). Fully functional at
// 390px: lines stack, text wraps, there is no horizontal scroll.

import { useArchStore } from "../store";
import { resolvePublicationText } from "../utils/publication";

export function PublicationFooter() {
  const publication = useArchStore((s) => s.publication);
  const darkMode = useArchStore((s) => s.darkMode);

  if (!publication) return null;

  const lines = publication.footer.always.map((line) =>
    resolvePublicationText(line, publication),
  );
  if (lines.length === 0) return null;

  return (
    <footer
      data-testid="publication-footer"
      className={`
        shrink-0 px-4 py-1.5 border-t text-[11px] leading-relaxed
        ${darkMode
          ? "bg-zinc-950/95 border-zinc-800 text-zinc-500"
          : "bg-white/95 border-zinc-200 text-zinc-400"}
      `}
    >
      <details className="sm:hidden">
        <summary className="min-h-8 cursor-pointer py-1 font-medium">About this {publication.access.visibility === "private-preview" ? "private " : ""}map</summary>
        <div className="flex flex-col gap-0.5 pb-2">
          {lines.map((line, i) => <p key={i} className="break-words">{line}</p>)}
        </div>
      </details>
      <div className="hidden flex-col gap-0.5 sm:flex">
        {lines.map((line, i) => (
          <p key={i} className="break-words">
            {line}
          </p>
        ))}
      </div>
    </footer>
  );
}
