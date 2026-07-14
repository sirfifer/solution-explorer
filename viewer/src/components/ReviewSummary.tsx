import { useState, useMemo } from "react";
import { useArchStore } from "../store";
import type { Annotation, Component } from "../types";
import { getTypeColors, TYPE_META } from "../utils/layout";
import { generateReviewPrompt, generateComponentPrompt } from "../utils/promptGenerator";
import { SelectionSetsSection } from "./SelectionSetsSection";

// Human-readable labels for sub-component targets
const SUB_TARGET_LABELS: Record<string, { label: string; icon: string }> = {
  "component-name": { label: "name", icon: "Aa" },
  "component-type": { label: "type", icon: "\u2B22" },
  "component-framework": { label: "framework", icon: "\u2699" },
  "component-port": { label: "port", icon: "\uD83D\uDD0C" },
  "component-purpose": { label: "purpose", icon: "\uD83D\uDCDD" },
  "component-pattern": { label: "pattern", icon: "\u2B22" },
};

// Sort order for target types within a group
const TARGET_ORDER: Record<string, number> = {
  "component": 0,
  "component-name": 1,
  "component-type": 2,
  "component-framework": 3,
  "component-port": 4,
  "component-purpose": 5,
  "component-pattern": 6,
  "file": 7,
  "symbol": 8,
};

interface ComponentGroup {
  componentId: string;
  component: Component;
  annotations: Annotation[];
}

export function ReviewSummary() {
  const {
    annotations,
    architecture,
    darkMode,
    setAnnotatingComponent,
    setAnnotatingTarget,
    deleteAnnotation,
    clearAllAnnotations,
    selectComponent,
    setActivePanel,
    getComponentById,
    selectionSets,
  } = useArchStore();

  const [copied, setCopied] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  if (!architecture) return null;

  // Group annotations by component
  const groups: ComponentGroup[] = useMemo(() => {
    const map = new Map<string, Annotation[]>();
    for (const a of annotations) {
      const arr = map.get(a.componentId) || [];
      arr.push(a);
      map.set(a.componentId, arr);
    }
    return Array.from(map.entries())
      .map(([componentId, anns]) => {
        const comp = getComponentById(componentId);
        if (!comp) return null;
        const sorted = [...anns].sort(
          (a, b) => (TARGET_ORDER[a.targetType] ?? 99) - (TARGET_ORDER[b.targetType] ?? 99),
        );
        return { componentId, component: comp, annotations: sorted } as ComponentGroup;
      })
      .filter((g): g is ComponentGroup => g !== null);
  }, [annotations, getComponentById]);

  // Orphaned annotations: their target component no longer exists in the current
  // architecture (for example after re-analysis renamed or removed it). Persisted
  // annotations must never be silently dropped, so surface them explicitly for
  // review instead of hiding them the way the component grouping does (F-VW-4).
  const orphaned: Annotation[] = useMemo(() => {
    return annotations.filter((a) => getComponentById(a.componentId) === null);
  }, [annotations, getComponentById]);

  const handleCopyAll = async () => {
    const prompt = generateReviewPrompt(annotations, architecture, getComponentById);
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
      window.open("vscode://");
    } catch {
      const w = window.open("", "_blank", "width=600,height=500");
      if (w) {
        w.document.write(`<pre style="white-space:pre-wrap;font-family:monospace;padding:20px">${prompt.replace(/</g, "&lt;")}</pre>`);
      }
    }
  };

  const handleClearAll = () => {
    if (confirmClear) {
      clearAllAnnotations();
      setConfirmClear(false);
      setActivePanel(null);
    } else {
      setConfirmClear(true);
      setTimeout(() => setConfirmClear(false), 3000);
    }
  };

  const handleNavigate = (componentId: string) => {
    const store = useArchStore.getState();
    if (store.reviewMode) useArchStore.setState({ reviewMode: false });
    selectComponent(componentId);
    useArchStore.setState({ reviewMode: true });
  };

  const handleEdit = (annotation: Annotation) => {
    if (annotation.targetType === "component") {
      setAnnotatingComponent(annotation.componentId);
    } else {
      setAnnotatingTarget({
        type: annotation.targetType,
        id: annotation.targetId,
        name: annotation.targetName,
        componentId: annotation.componentId,
        targetContext: annotation.targetContext,
      });
    }
  };

  const renderAnnotation = (annotation: Annotation) => {
    const comp = getComponentById(annotation.componentId);
    if (!comp) return null;

    const isWholeComponent = annotation.targetType === "component";
    const isSubComponent = annotation.targetType.startsWith("component-");
    const subMeta = isSubComponent ? SUB_TARGET_LABELS[annotation.targetType] : null;

    // Display name for the annotation target
    const displayName = isWholeComponent
      ? "General feedback"
      : isSubComponent
        ? annotation.targetType === "component-pattern"
          ? `Pattern: ${annotation.targetContext?.patternValue || annotation.targetName}`
          : subMeta?.label || annotation.targetType.replace("component-", "")
        : annotation.targetType === "file"
          ? (annotation.targetName.split("/").pop() || annotation.targetName)
          : annotation.targetName;

    // Icon for annotation type
    const displayIcon = isWholeComponent
      ? "\u2B22"
      : isSubComponent
        ? subMeta?.icon || "\u2B22"
        : annotation.targetType === "file"
          ? "\uD83D\uDCC4"
          : "\u2666";

    // Badge style
    const badgeStyle = isSubComponent
      ? darkMode ? "bg-blue-900/40 text-blue-300" : "bg-blue-100 text-blue-600"
      : darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-500";

    return (
      <div
        key={annotation.id}
        className={`mx-2 mb-2 rounded-lg border ${darkMode ? "border-zinc-800 bg-zinc-900/50" : "border-zinc-100 bg-zinc-50/50"}`}
      >
        {/* Header */}
        <div className={`px-3 py-2 border-b ${darkMode ? "border-zinc-800/50" : "border-zinc-100"}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="text-[10px] shrink-0">{displayIcon}</span>
              <span className={`text-xs font-medium truncate ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
                {displayName}
              </span>
              <span className={`text-[9px] px-1 py-0.5 rounded shrink-0 ${badgeStyle}`}>
                {isWholeComponent ? "component" : isSubComponent ? (subMeta?.label || "property") : annotation.targetType}
              </span>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={() => handleEdit(annotation)}
                className={`p-1 rounded text-[10px] ${darkMode ? "hover:bg-zinc-800 text-zinc-500" : "hover:bg-zinc-200 text-zinc-400"}`}
                title="Edit"
              >
                &#x270F;&#xFE0F;
              </button>
              <button
                onClick={() => deleteAnnotation(annotation.id)}
                className={`p-1 rounded text-[10px] ${darkMode ? "hover:bg-zinc-800 text-zinc-500" : "hover:bg-zinc-200 text-zinc-400"}`}
                title="Delete"
              >
                &#x1F5D1;&#xFE0F;
              </button>
            </div>
          </div>
        </div>

        {/* Annotation text */}
        <div className="px-3 py-2">
          <p className={`text-xs leading-relaxed whitespace-pre-wrap ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
            {annotation.text}
          </p>
        </div>
      </div>
    );
  };

  // Render an annotation whose target component no longer exists. It cannot be
  // rendered by renderAnnotation (which resolves the live component), so show the
  // stored target label and text with a delete affordance.
  const renderOrphanedAnnotation = (annotation: Annotation) => {
    const label = annotation.targetName || annotation.componentId;
    return (
      <div
        key={annotation.id}
        className={`mx-2 mb-2 rounded-lg border ${darkMode ? "border-amber-900/40 bg-amber-950/20" : "border-amber-100 bg-amber-50/50"}`}
      >
        <div className={`px-3 py-2 border-b ${darkMode ? "border-amber-900/30" : "border-amber-100"}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className={`text-xs font-medium truncate ${darkMode ? "text-amber-200" : "text-amber-800"}`}>
                {label}
              </span>
              <span className={`text-[9px] px-1 py-0.5 rounded shrink-0 ${darkMode ? "bg-amber-900/40 text-amber-300" : "bg-amber-100 text-amber-700"}`}>
                {annotation.targetType}
              </span>
            </div>
            <button
              onClick={() => deleteAnnotation(annotation.id)}
              className={`p-1 rounded text-[10px] shrink-0 ${darkMode ? "hover:bg-zinc-800 text-zinc-500" : "hover:bg-zinc-200 text-zinc-400"}`}
              title="Delete"
            >
              &#x1F5D1;&#xFE0F;
            </button>
          </div>
        </div>
        <div className="px-3 py-2">
          <p className={`text-xs leading-relaxed whitespace-pre-wrap ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
            {annotation.text}
          </p>
        </div>
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className={`px-4 py-3 border-b flex items-center justify-between ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        <div>
          <h2 className={`text-xs font-semibold uppercase tracking-wider ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            Review Summary
          </h2>
          <p className={`text-[11px] mt-0.5 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            {annotations.length} annotation{annotations.length !== 1 ? "s" : ""}
            {groups.length > 1 && (
              <span>
                {" \u00B7 "}
                {groups.length} component{groups.length !== 1 ? "s" : ""}
              </span>
            )}
          </p>
        </div>
        <button
          onClick={() => setActivePanel(null)}
          className={`p-1.5 rounded-lg text-xs ${darkMode ? "hover:bg-zinc-800 text-zinc-500" : "hover:bg-zinc-100 text-zinc-400"}`}
          title="Close"
        >
          &#x2715;
        </button>
      </div>

      {/* Annotations list, grouped by component, plus selection sets */}
      <div className="flex-1 overflow-y-auto">
        {annotations.length === 0 && selectionSets.length === 0 ? (
          <div className={`px-4 py-8 text-center text-sm ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            No annotations yet. Click on components in the graph to add feedback,
            or create a selection set from a finding, concern, or search.
          </div>
        ) : (
          <div className="py-2">
            {groups.map((group) => (
              <ComponentGroupSection
                key={group.componentId}
                group={group}
                darkMode={darkMode}
                architecture={architecture}
                getComponentById={getComponentById}
                onNavigate={handleNavigate}
                renderAnnotation={renderAnnotation}
              />
            ))}
            <SelectionSetsSection darkMode={darkMode} />
            {orphaned.length > 0 && (
              <div className="mt-2" data-testid="orphaned-annotations">
                <div className={`px-4 pt-3 pb-2 flex items-center gap-1.5 ${darkMode ? "text-amber-400" : "text-amber-600"}`}>
                  <span className="text-xs">{"⚠"}</span>
                  <span className="text-xs font-semibold truncate">
                    Orphaned feedback
                  </span>
                  <span className={`text-[9px] px-1 py-0.5 rounded shrink-0 ${darkMode ? "bg-amber-900/40 text-amber-300" : "bg-amber-100 text-amber-700"}`}>
                    {orphaned.length}
                  </span>
                </div>
                <p className={`px-4 pb-2 text-[11px] leading-relaxed ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                  These annotations target components no longer in the architecture.
                  They are kept so re-analysis does not destroy your feedback.
                </p>
                {orphaned.map(renderOrphanedAnnotation)}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer actions */}
      {annotations.length > 0 && (
        <div className={`px-4 py-3 border-t space-y-2 ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          <button
            onClick={handleCopyAll}
            className={`
              w-full py-2 rounded-lg text-sm font-medium transition-colors
              ${copied
                ? darkMode
                  ? "bg-green-600/20 text-green-300"
                  : "bg-green-100 text-green-700"
                : darkMode
                  ? "bg-blue-600 text-white hover:bg-blue-500"
                  : "bg-blue-500 text-white hover:bg-blue-600"
              }
            `}
          >
            {copied ? "Copied! Paste into Claude Code" : "Copy All to Claude Code"}
          </button>

          <button
            onClick={handleClearAll}
            className={`
              w-full py-1.5 rounded-lg text-xs transition-colors
              ${confirmClear
                ? "bg-red-500/20 text-red-400"
                : darkMode
                  ? "text-zinc-500 hover:bg-zinc-800 hover:text-zinc-400"
                  : "text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600"
              }
            `}
          >
            {confirmClear ? "Confirm: Clear All Annotations" : "Clear All"}
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Per-component group section ─────────────────────────────────────────────

function ComponentGroupSection({
  group,
  darkMode,
  architecture,
  getComponentById,
  onNavigate,
  renderAnnotation,
}: {
  group: ComponentGroup;
  darkMode: boolean;
  architecture: NonNullable<ReturnType<typeof useArchStore.getState>["architecture"]>;
  getComponentById: (id: string) => Component | null;
  onNavigate: (componentId: string) => void;
  renderAnnotation: (annotation: Annotation) => React.ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  const comp = group.component;
  const colors = getTypeColors(comp.type, darkMode);
  const meta = TYPE_META[comp.type];

  const handleCopyComponent = async () => {
    const prompt = generateComponentPrompt(comp, group.annotations, architecture, getComponentById);
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const w = window.open("", "_blank", "width=600,height=500");
      if (w) {
        w.document.write(`<pre style="white-space:pre-wrap;font-family:monospace;padding:20px">${prompt.replace(/</g, "&lt;")}</pre>`);
      }
    }
  };

  return (
    <div className={`mb-3 ${darkMode ? "border-b border-zinc-800/50" : "border-b border-zinc-100"} last:border-b-0`}>
      {/* Component group header */}
      <div className={`px-4 pt-3 pb-2 flex items-center justify-between`}>
        <button
          onClick={() => onNavigate(group.componentId)}
          className="flex items-center gap-1.5 hover:underline min-w-0"
        >
          {meta?.icon && <span className="text-xs">{meta.icon}</span>}
          <span className={`text-xs font-semibold truncate ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
            {comp.name}
          </span>
          <span className={`text-[9px] px-1 py-0.5 rounded shrink-0 ${colors.badge}`}>
            {meta?.label || comp.type}
          </span>
        </button>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            {group.annotations.length}
          </span>
          <button
            onClick={handleCopyComponent}
            className={`
              text-[10px] px-2 py-1 rounded-md font-medium transition-colors
              ${copied
                ? darkMode ? "bg-green-600/20 text-green-300" : "bg-green-100 text-green-700"
                : darkMode ? "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200" : "bg-zinc-100 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-700"
              }
            `}
            title={`Copy feedback for ${comp.name}`}
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
      </div>

      {/* Annotations in this group */}
      {group.annotations.map(renderAnnotation)}
    </div>
  );
}
