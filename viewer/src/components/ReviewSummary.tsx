import { useState } from "react";
import { useArchStore } from "../store";
import type { Annotation, AnnotationTarget } from "../types";
import { getTypeColors, TYPE_META } from "../utils/layout";
import { generateReviewPrompt } from "../utils/promptGenerator";

const TARGET_GROUP_META: Record<AnnotationTarget, { label: string; icon: string }> = {
  component: { label: "Components", icon: "\u2B22" },
  file: { label: "Files", icon: "\uD83D\uDCC4" },
  symbol: { label: "Symbols", icon: "\u2666" },
};

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
  } = useArchStore();

  const [copied, setCopied] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  if (!architecture) return null;

  // Group annotations by target type
  const grouped: Record<AnnotationTarget, Annotation[]> = {
    component: [],
    file: [],
    symbol: [],
  };
  for (const a of annotations) {
    const t = a.targetType || "component";
    grouped[t].push(a);
  }

  const handleCopyToClaudeCode = async () => {
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
    store.reviewMode && useArchStore.setState({ reviewMode: false });
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
      });
    }
  };

  const renderAnnotation = (annotation: Annotation) => {
    const comp = getComponentById(annotation.componentId);
    if (!comp) return null;
    const colors = getTypeColors(comp.type, darkMode);
    const meta = TYPE_META[comp.type];
    const isComponent = annotation.targetType === "component";

    return (
      <div
        key={annotation.id}
        className={`mx-2 mb-2 rounded-lg border ${darkMode ? "border-zinc-800 bg-zinc-900/50" : "border-zinc-100 bg-zinc-50/50"}`}
      >
        {/* Header */}
        <div className={`px-3 py-2 border-b ${darkMode ? "border-zinc-800/50" : "border-zinc-100"}`}>
          <div className="flex items-center justify-between">
            <button
              onClick={() => handleNavigate(annotation.componentId)}
              className="flex items-center gap-1.5 hover:underline min-w-0"
            >
              {isComponent ? (
                <>
                  {meta?.icon && <span className="text-xs">{meta.icon}</span>}
                  <span className={`text-xs font-medium truncate ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
                    {comp.name}
                  </span>
                  <span className={`text-[9px] px-1 py-0.5 rounded shrink-0 ${colors.badge}`}>
                    {meta?.label || comp.type}
                  </span>
                </>
              ) : (
                <>
                  <span className="text-[10px] shrink-0">
                    {annotation.targetType === "file" ? "\uD83D\uDCC4" : "\u2666"}
                  </span>
                  <span className={`text-xs font-medium truncate ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
                    {annotation.targetType === "file"
                      ? (annotation.targetName.split("/").pop() || annotation.targetName)
                      : annotation.targetName}
                  </span>
                  <span className={`text-[9px] px-1 py-0.5 rounded shrink-0 ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-500"}`}>
                    {annotation.targetType}
                  </span>
                </>
              )}
            </button>
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
          {/* Show parent component for file/symbol annotations */}
          {!isComponent && (
            <p className={`text-[10px] mt-0.5 truncate ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
              in {comp.name}
            </p>
          )}
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

  const groupOrder: AnnotationTarget[] = ["component", "file", "symbol"];
  const nonEmptyGroups = groupOrder.filter((t) => grouped[t].length > 0);

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
            {nonEmptyGroups.length > 1 && (
              <span>
                {" \u00B7 "}
                {nonEmptyGroups.map((t) => `${grouped[t].length} ${TARGET_GROUP_META[t].label.toLowerCase()}`).join(", ")}
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

      {/* Annotations list, grouped by type */}
      <div className="flex-1 overflow-y-auto">
        {annotations.length === 0 ? (
          <div className={`px-4 py-8 text-center text-sm ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            No annotations yet. Click on components in the graph to add feedback.
          </div>
        ) : (
          <div className="py-2">
            {nonEmptyGroups.map((targetType) => (
              <div key={targetType}>
                {/* Group header (only if multiple groups) */}
                {nonEmptyGroups.length > 1 && (
                  <div className={`px-4 pt-3 pb-1.5 flex items-center gap-1.5 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                    <span className="text-[10px]">{TARGET_GROUP_META[targetType].icon}</span>
                    <span className="text-[10px] font-semibold uppercase tracking-wider">
                      {TARGET_GROUP_META[targetType].label}
                    </span>
                    <span className={`text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-300"}`}>
                      ({grouped[targetType].length})
                    </span>
                  </div>
                )}
                {grouped[targetType].map(renderAnnotation)}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer actions */}
      {annotations.length > 0 && (
        <div className={`px-4 py-3 border-t space-y-2 ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          <button
            onClick={handleCopyToClaudeCode}
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
            {copied ? "Copied! Paste into Claude Code" : "Copy to Claude Code"}
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
