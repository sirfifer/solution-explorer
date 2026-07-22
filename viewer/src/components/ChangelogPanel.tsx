import { useState, useEffect, memo } from "react";
import type { ChangelogEntry, ChangelogChange } from "../types";
import { useArchStore } from "../store";
import { formatRelativeTime, getTypeColors, TYPE_META } from "../utils/layout";

// Icons for change kinds
const KIND_ICONS: Record<string, { icon: string; label: string }> = {
  component_added: { icon: "+", label: "Added" },
  component_removed: { icon: "\u2212", label: "Removed" },
  component_modified: { icon: "~", label: "Modified" },
  relationship_added: { icon: "+", label: "Connected" },
  relationship_removed: { icon: "\u2212", label: "Disconnected" },
};

function kindColor(kind: string, darkMode: boolean): string {
  if (kind.includes("added")) return darkMode ? "text-emerald-400" : "text-emerald-600";
  if (kind.includes("removed")) return darkMode ? "text-red-400" : "text-red-600";
  return darkMode ? "text-amber-400" : "text-amber-600";
}

function kindBadgeColor(kind: string, darkMode: boolean): string {
  if (kind.includes("added")) return darkMode ? "bg-emerald-500/15 text-emerald-400" : "bg-emerald-100 text-emerald-700";
  if (kind.includes("removed")) return darkMode ? "bg-red-500/15 text-red-400" : "bg-red-100 text-red-700";
  return darkMode ? "bg-amber-500/15 text-amber-400" : "bg-amber-100 text-amber-700";
}

// Clickable component name that navigates to the node in the graph
function ComponentLink({ id, name, darkMode }: { id: string; name: string; darkMode: boolean }) {
  const { navigateToComponent, getComponentById } = useArchStore();
  const exists = getComponentById(id) !== null;

  if (!exists) {
    return (
      <span className={`${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
        {name} <span className="text-[10px]">(removed)</span>
      </span>
    );
  }

  return (
    <button
      className={`text-left hover:underline ${darkMode ? "text-blue-400 hover:text-blue-300" : "text-blue-600 hover:text-blue-500"}`}
      onClick={(e) => {
        e.stopPropagation();
        navigateToComponent(id);
      }}
    >
      {name}
    </button>
  );
}

// Single change item within an entry
function ChangeItem({ change, darkMode }: { change: ChangelogChange; darkMode: boolean }) {
  const kindInfo = KIND_ICONS[change.kind] ?? { icon: "?", label: change.kind };
  const isRelationship = change.kind.startsWith("relationship_");

  return (
    <div className={`flex items-start gap-2 py-1 px-2 rounded ${darkMode ? "hover:bg-zinc-800/30" : "hover:bg-zinc-50"}`}>
      {/* Kind icon */}
      <span className={`w-4 h-4 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5 ${kindColor(change.kind, darkMode)}`}>
        {kindInfo.icon}
      </span>

      <div className="flex-1 min-w-0">
        {/* Component/relationship name as clickable link */}
        <div className="flex items-center gap-1.5 flex-wrap text-xs">
          {isRelationship && change.source_id && change.dest_id ? (
            <>
              <ComponentLink id={change.source_id} name={change.source_name ?? change.source_id} darkMode={darkMode} />
              <span className={darkMode ? "text-zinc-600" : "text-zinc-400"}>{"\u2192"}</span>
              <ComponentLink id={change.dest_id} name={change.dest_name ?? change.dest_id} darkMode={darkMode} />
            </>
          ) : (
            <>
              <ComponentLink id={change.target_id} name={change.target_name} darkMode={darkMode} />
              {change.target_type && (
                <span className={`text-[9px] px-1 py-0.5 rounded ${getTypeColors(change.target_type, darkMode).badge} shrink-0`}>
                  {TYPE_META[change.target_type]?.icon || change.target_type.slice(0, 3)}
                </span>
              )}
            </>
          )}
        </div>

        {/* Detail text */}
        {change.detail && (
          <div className={`text-[11px] mt-0.5 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            {change.detail}
          </div>
        )}
      </div>
    </div>
  );
}

// Single changelog entry card
const ChangelogEntryCard = memo(function ChangelogEntryCard({
  entry,
  darkMode,
}: {
  entry: ChangelogEntry;
  darkMode: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const { isChangelogEntryRead, markChangelogEntryRead } = useArchStore();
  const isRead = isChangelogEntryRead(entry.serial);

  // Mark read on the user's own view action, never on a timer (owner's
  // notification-persistence principle: an important notice persists until an
  // actual viewing or clearing behavior). Expanding the entry to read its
  // change list is that view; the "Mark all as read" control is the explicit
  // clear. A badge that erased itself on a timer could not be relied on to be
  // seen (GUI run finding V11.1).
  const toggleExpanded = () => {
    if (!isRead) markChangelogEntryRead(entry.serial);
    setExpanded((v) => !v);
  };

  // Summary badges (counts by kind)
  const counts = entry.changes.reduce(
    (acc, c) => {
      if (c.kind.includes("added")) acc.added++;
      else if (c.kind.includes("removed")) acc.removed++;
      else acc.modified++;
      return acc;
    },
    { added: 0, removed: 0, modified: 0 },
  );

  return (
    <div className={`${darkMode ? "border-zinc-800/50" : "border-zinc-100"}`}>
      <button
        className={`w-full text-left flex items-start gap-2 px-3 py-2 text-xs rounded-lg transition-colors ${
          darkMode ? "hover:bg-zinc-800/50" : "hover:bg-zinc-50"
        }`}
        onClick={toggleExpanded}
      >
        {/* Unread dot */}
        <span className="w-2 shrink-0 mt-1.5">
          {!isRead && <span className="block w-2 h-2 rounded-full bg-blue-500" />}
        </span>

        <div className="flex-1 min-w-0">
          {/* Timestamp + scan type */}
          <div className="flex items-center gap-2">
            <span className={`text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
              {formatRelativeTime(entry.timestamp)}
            </span>
            {entry.commit_sha && (
              <code className={`text-[10px] px-1 py-0.5 rounded font-mono ${
                darkMode ? "bg-zinc-800 text-zinc-500" : "bg-zinc-100 text-zinc-500"
              }`}>
                {entry.commit_sha.slice(0, 7)}
              </code>
            )}
          </div>

          {/* Summary */}
          <div className={`mt-0.5 ${isRead ? "" : "font-medium"} ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
            {entry.summary}
          </div>

          {/* Diff count badges */}
          <div className="flex items-center gap-1.5 mt-1">
            {counts.added > 0 && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${kindBadgeColor("added", darkMode)}`}>
                +{counts.added}
              </span>
            )}
            {counts.modified > 0 && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${kindBadgeColor("modified", darkMode)}`}>
                ~{counts.modified}
              </span>
            )}
            {counts.removed > 0 && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${kindBadgeColor("removed", darkMode)}`}>
                -{counts.removed}
              </span>
            )}
          </div>
        </div>

        {/* Expand chevron */}
        <span className={`text-[10px] shrink-0 mt-1 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
          {expanded ? "\u25BC" : "\u25B6"}
        </span>
      </button>

      {/* Expanded change details */}
      {expanded && (
        <div className={`ml-4 mr-2 mb-2 border-l-2 pl-2 ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          {entry.changes.map((change, i) => (
            <ChangeItem key={`${change.kind}-${change.target_id}-${i}`} change={change} darkMode={darkMode} />
          ))}
        </div>
      )}
    </div>
  );
});

export function ChangelogPanel() {
  const { architecture, darkMode, getUnreadChangelogCount, markAllChangelogRead } = useArchStore();
  const [expanded, setExpanded] = useState(false);

  const changelog = architecture?.changelog;
  const unreadCount = getUnreadChangelogCount();

  // Auto-expand when there are unread entries
  useEffect(() => {
    if (unreadCount > 0) setExpanded(true);
  }, [unreadCount]);

  // Don't render anything if no changelog data
  if (!changelog || changelog.length === 0) return null;

  // Sort entries most recent first
  const sorted = [...changelog].sort((a, b) => b.serial - a.serial);

  return (
    <div className={`border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
      {/* Section header */}
      <button
        className={`w-full flex items-center gap-2 px-4 py-2 text-left transition-colors ${
          darkMode ? "hover:bg-zinc-800/30" : "hover:bg-zinc-50"
        }`}
        onClick={() => setExpanded(!expanded)}
      >
        {/* Bell icon */}
        <svg className={`w-3.5 h-3.5 shrink-0 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0" />
        </svg>

        <span className={`text-[10px] font-semibold uppercase tracking-wider flex-1 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
          What's New
        </span>

        {/* Unread count badge */}
        {unreadCount > 0 && (
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-blue-500 text-white min-w-[18px] text-center">
            {unreadCount}
          </span>
        )}

        {/* Expand/collapse */}
        <span className={`text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
          {expanded ? "\u25BC" : "\u25B6"}
        </span>
      </button>

      {/* Entry list */}
      {expanded && (
        <div className="max-h-80 overflow-y-auto">
          {/* Mark all read button */}
          {unreadCount > 0 && (
            <div className="px-4 pb-1">
              <button
                className={`text-[10px] ${darkMode ? "text-blue-400 hover:text-blue-300" : "text-blue-600 hover:text-blue-500"}`}
                onClick={(e) => {
                  e.stopPropagation();
                  markAllChangelogRead();
                }}
              >
                Mark all as read
              </button>
            </div>
          )}

          {sorted.map((entry) => (
            <ChangelogEntryCard key={entry.serial} entry={entry} darkMode={darkMode} />
          ))}
        </div>
      )}
    </div>
  );
}
