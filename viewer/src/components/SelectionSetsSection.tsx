import { useState } from "react";
import { useArchStore } from "../store";
import type { SelectionSet, SetMember } from "../types";
import { generateDirective } from "../utils/directiveGenerator";

/**
 * Selection Sets section of the review panel (P6-9, LENS-DESIGN section 10).
 *
 * Renders each set with its shared intent, member list (with per-member notes
 * and orphaned-member handling consistent with P1-3), and a directive export
 * that produces the structured work order (markdown plus embedded JSON) for an
 * AI executor, with copy-to-clipboard and download.
 */
export function SelectionSetsSection({ darkMode }: { darkMode: boolean }) {
  const sets = useArchStore((s) => s.selectionSets);
  if (sets.length === 0) return null;
  return (
    <div className="mt-2" data-testid="selection-sets">
      <div className={`px-4 pt-3 pb-2 flex items-center gap-1.5 ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
        <span className="text-xs">{"▣"}</span>
        <span className="text-xs font-semibold">Selection sets</span>
        <span className={`text-[9px] px-1 py-0.5 rounded shrink-0 ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-500"}`}>
          {sets.length}
        </span>
      </div>
      {sets.map((set) => (
        <SelectionSetCard key={set.id} set={set} darkMode={darkMode} />
      ))}
    </div>
  );
}

function downloadText(filename: string, text: string) {
  try {
    const blob = new Blob([text], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    // Revoke on the next tick so the click has taken effect.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  } catch {
    // Download unavailable (unlikely in a browser); copy remains the fallback.
  }
}

function SelectionSetCard({ set, darkMode }: { set: SelectionSet; darkMode: boolean }) {
  const {
    architecture,
    getComponentById,
    getSetAnnotation,
    renameSet,
    deleteSet,
    setSetIntent,
    setSetMemberNote,
    navigateToSetMember,
  } = useArchStore();

  const annotation = getSetAnnotation(set.id);
  const [expanded, setExpanded] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [copied, setCopied] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  // Exemption reasons keyed by member ref. A non-blank reason marks the member
  // exempt (removed from the work order). The checkbox is "in scope".
  const [exemptReasons, setExemptReasons] = useState<Record<string, string>>({});
  const [acceptanceText, setAcceptanceText] = useState("");

  if (!architecture) return null;

  const orphanCount = set.members.filter((m) => getComponentById(m.componentId) === null).length;

  const buildOptions = () => ({
    exemptions: exemptReasons,
    acceptanceCriteria: acceptanceText.split("\n"),
  });

  const handleCopy = async () => {
    const { markdown } = generateDirective(set, annotation, architecture, buildOptions());
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      const w = window.open("", "_blank", "width=700,height=600");
      if (w) {
        w.document.write(`<pre style="white-space:pre-wrap;font-family:monospace;padding:20px">${markdown.replace(/</g, "&lt;")}</pre>`);
      }
    }
  };

  const handleDownload = () => {
    const { markdown } = generateDirective(set, annotation, architecture, buildOptions());
    const safeName = set.name.replace(/[^a-z0-9]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase() || "directive";
    downloadText(`directive-${safeName}.md`, markdown);
  };

  const toggleExempt = (m: SetMember) => {
    setExemptReasons((prev) => {
      const next = { ...prev };
      if (m.ref in next) {
        delete next[m.ref];
      } else {
        next[m.ref] = "";
      }
      return next;
    });
  };

  const border = darkMode ? "border-zinc-800 bg-zinc-900/50" : "border-zinc-100 bg-zinc-50/50";

  return (
    <div className={`mx-2 mb-2 rounded-lg border ${border}`} data-testid="selection-set-card">
      {/* Header: name + origin + count + delete */}
      <div className={`px-3 py-2 border-b ${darkMode ? "border-zinc-800/50" : "border-zinc-100"}`}>
        <div className="flex items-center justify-between gap-2">
          <input
            aria-label="Set name"
            value={set.name}
            onChange={(e) => renameSet(set.id, e.target.value)}
            className={`flex-1 min-w-0 bg-transparent text-xs font-medium outline-none ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}
          />
          <button
            onClick={() => {
              if (confirmDelete) {
                deleteSet(set.id);
              } else {
                setConfirmDelete(true);
                setTimeout(() => setConfirmDelete(false), 3000);
              }
            }}
            className={`p-1 rounded text-[10px] shrink-0 ${confirmDelete ? "text-red-400" : darkMode ? "hover:bg-zinc-800 text-zinc-500" : "hover:bg-zinc-200 text-zinc-400"}`}
            title={confirmDelete ? "Confirm delete" : "Delete set"}
          >
            {confirmDelete ? "Confirm" : "🗑️"}
          </button>
        </div>
        <div className="flex items-center gap-1.5 mt-1">
          <span className={`text-[9px] px-1 py-0.5 rounded ${darkMode ? "bg-blue-900/40 text-blue-300" : "bg-blue-100 text-blue-600"}`}>
            {set.origin.split(":")[0]}
          </span>
          <span className={`text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            {set.members.length} member{set.members.length !== 1 ? "s" : ""}
          </span>
          {orphanCount > 0 && (
            <span className={`text-[9px] px-1 py-0.5 rounded ${darkMode ? "bg-amber-900/40 text-amber-300" : "bg-amber-100 text-amber-700"}`}>
              {orphanCount} orphaned
            </span>
          )}
        </div>
      </div>

      {/* Shared intent */}
      <div className="px-3 py-2">
        <label className={`block text-[10px] font-semibold uppercase tracking-wider mb-1 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
          Shared intent
        </label>
        <textarea
          aria-label="Set intent"
          value={annotation?.intent ?? ""}
          onChange={(e) => setSetIntent(set.id, e.target.value)}
          placeholder="State the shared intent once, e.g. all members log through the same shared logger."
          rows={2}
          className={`w-full text-xs rounded-md px-2 py-1.5 outline-none resize-y ${darkMode ? "bg-zinc-800 text-zinc-200 placeholder-zinc-600" : "bg-white border border-zinc-200 text-zinc-800 placeholder-zinc-400"}`}
        />
      </div>

      {/* Members (collapsible) */}
      <div className="px-3 pb-2">
        <button
          onClick={() => setExpanded((v) => !v)}
          className={`text-[10px] ${darkMode ? "text-zinc-400 hover:text-zinc-200" : "text-zinc-500 hover:text-zinc-700"}`}
        >
          {expanded ? "▾" : "▸"} Members ({set.members.length})
        </button>
        {expanded && (
          <div className="mt-1.5 space-y-1.5" data-testid="set-members">
            {set.members.map((m) => {
              const orphaned = getComponentById(m.componentId) === null;
              const note = annotation?.memberNotes.find((n) => n.memberRef === m.ref)?.note ?? "";
              return (
                <div key={m.ref} className={`rounded-md px-2 py-1.5 ${darkMode ? "bg-zinc-800/50" : "bg-white border border-zinc-100"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <button
                      onClick={() => navigateToSetMember(m)}
                      disabled={orphaned}
                      className={`text-[11px] truncate text-left ${orphaned ? (darkMode ? "text-amber-300" : "text-amber-700") : darkMode ? "text-zinc-300 hover:text-blue-300" : "text-zinc-700 hover:text-blue-600"}`}
                      title={m.file ?? m.componentId}
                    >
                      {m.label}
                      {m.file && m.lineStart != null ? ` :${m.lineStart}` : ""}
                    </button>
                    {orphaned && (
                      <span className={`text-[9px] px-1 rounded shrink-0 ${darkMode ? "bg-amber-900/40 text-amber-300" : "bg-amber-100 text-amber-700"}`}>
                        orphaned
                      </span>
                    )}
                  </div>
                  <input
                    aria-label={`Note for ${m.label}`}
                    value={note}
                    onChange={(e) => setSetMemberNote(set.id, m.ref, e.target.value)}
                    placeholder="Optional per-member note"
                    className={`w-full mt-1 text-[10px] rounded px-1.5 py-1 outline-none ${darkMode ? "bg-zinc-900 text-zinc-300 placeholder-zinc-600" : "bg-zinc-50 text-zinc-600 placeholder-zinc-400"}`}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Export directive */}
      <div className={`px-3 py-2 border-t ${darkMode ? "border-zinc-800/50" : "border-zinc-100"}`}>
        <button
          onClick={() => setShowExport((v) => !v)}
          className={`text-[10px] font-medium ${darkMode ? "text-zinc-400 hover:text-zinc-200" : "text-zinc-500 hover:text-zinc-700"}`}
        >
          {showExport ? "▾" : "▸"} Export directive
        </button>
        {showExport && (
          <div className="mt-2 space-y-2" data-testid="directive-export">
            {/* Exemptions */}
            <div>
              <div className={`text-[10px] font-semibold uppercase tracking-wider mb-1 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                Exemptions (uncheck to leave a member out)
              </div>
              {set.members.map((m) => {
                const exempt = m.ref in exemptReasons;
                return (
                  <div key={m.ref} className="mb-1">
                    <label className="flex items-center gap-1.5 text-[10px] cursor-pointer">
                      <input
                        type="checkbox"
                        checked={!exempt}
                        onChange={() => toggleExempt(m)}
                        aria-label={`Include ${m.label}`}
                      />
                      <span className={`truncate ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>{m.label}</span>
                    </label>
                    {exempt && (
                      <input
                        aria-label={`Exemption reason for ${m.label}`}
                        value={exemptReasons[m.ref]}
                        onChange={(e) =>
                          setExemptReasons((prev) => ({ ...prev, [m.ref]: e.target.value }))
                        }
                        placeholder="Reason required to exempt this member"
                        className={`w-full mt-1 text-[10px] rounded px-1.5 py-1 outline-none ${exemptReasons[m.ref].trim().length === 0 ? "ring-1 ring-red-400/60" : ""} ${darkMode ? "bg-zinc-900 text-zinc-300 placeholder-zinc-600" : "bg-zinc-50 text-zinc-600 placeholder-zinc-400"}`}
                      />
                    )}
                  </div>
                );
              })}
            </div>
            {/* Acceptance criteria */}
            <div>
              <div className={`text-[10px] font-semibold uppercase tracking-wider mb-1 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                Acceptance criteria (one per line; origin suggestions are added automatically)
              </div>
              <textarea
                aria-label="Acceptance criteria"
                value={acceptanceText}
                onChange={(e) => setAcceptanceText(e.target.value)}
                rows={2}
                placeholder="Add conditions this directive must satisfy to be done."
                className={`w-full text-[10px] rounded-md px-2 py-1.5 outline-none resize-y ${darkMode ? "bg-zinc-800 text-zinc-200 placeholder-zinc-600" : "bg-white border border-zinc-200 text-zinc-800 placeholder-zinc-400"}`}
              />
            </div>
            {/* Actions */}
            <div className="flex gap-2">
              <button
                onClick={handleCopy}
                className={`flex-1 py-1.5 rounded-md text-[11px] font-medium ${copied ? (darkMode ? "bg-green-600/20 text-green-300" : "bg-green-100 text-green-700") : darkMode ? "bg-blue-600 text-white hover:bg-blue-500" : "bg-blue-500 text-white hover:bg-blue-600"}`}
              >
                {copied ? "Copied directive" : "Copy directive"}
              </button>
              <button
                onClick={handleDownload}
                className={`flex-1 py-1.5 rounded-md text-[11px] font-medium ${darkMode ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700" : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"}`}
              >
                Download .md
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
