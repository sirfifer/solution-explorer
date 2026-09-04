// Product attribution is always present. Publication footer lines are appended
// when a valid publication.json sidecar is present.
// Design authority: docs/publication/PUBLICATION-METADATA.md (placement rule 4:
// footer content at the bottom, always region on every page; tool attribution is
// footer boilerplate and is always present).
//
// Pure presentation. Fully functional at 390px: lines stack, text wraps, and
// there is no horizontal scroll.

import { useArchStore } from "../store";
import { resolvePublicationText } from "../utils/publication";
import { SYSCORPUS } from "../utils/product";

export function PublicationFooter() {
  const publication = useArchStore((s) => s.publication);
  const darkMode = useArchStore((s) => s.darkMode);

  const lines = publication
    ? publication.footer.always.map((line) => resolvePublicationText(line, publication))
    : [];

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
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <p className="break-words">
          <a href={SYSCORPUS.url} target="_blank" rel="noopener noreferrer" className="font-bold text-cyan-500 hover:underline">{SYSCORPUS.name}</a>
          <span> · {SYSCORPUS.descriptor}</span>
        </p>
        <p className="break-words">{SYSCORPUS.copyright} <a href={SYSCORPUS.url} target="_blank" rel="noopener noreferrer" className="hover:text-cyan-500 hover:underline">syscorpus.com</a></p>
      </div>
      {publication && lines.length > 0 && <>
        <details className="mt-1 sm:hidden">
          <summary className="min-h-8 cursor-pointer py-1 font-medium">About this {publication.access.visibility === "private-preview" ? "private " : ""}map</summary>
          <div className="flex flex-col gap-0.5 pb-2">
            {lines.map((line, i) => <p key={i} className="break-words">{line}</p>)}
          </div>
        </details>
        <div className="mt-1 hidden flex-col gap-0.5 border-t border-current/10 pt-1 sm:flex">
          {lines.map((line, i) => (
            <p key={i} className="break-words">
              {line}
            </p>
          ))}
        </div>
      </>}
    </footer>
  );
}
