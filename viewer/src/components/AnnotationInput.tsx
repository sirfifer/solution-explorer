import { useState, useEffect, useRef } from "react";
import { useArchStore } from "../store";
import { getTypeColors, TYPE_META } from "../utils/layout";

export function AnnotationInput() {
  const {
    annotatingComponentId,
    annotatingTarget,
    annotations,
    darkMode,
    setAnnotatingComponent,
    addAnnotation,
    deleteAnnotation,
    getComponentById,
  } = useArchStore();

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const component = annotatingComponentId ? getComponentById(annotatingComponentId) : null;
  const targetType = annotatingTarget?.type ?? "component";
  const targetId = annotatingTarget?.id ?? annotatingComponentId ?? "";
  const targetName = annotatingTarget?.name ?? component?.name ?? "";

  const existing = annotations.find((a) =>
    a.targetType === targetType && a.targetId === targetId
  );
  const [text, setText] = useState("");

  useEffect(() => {
    setText(existing?.text || "");
    setTimeout(() => textareaRef.current?.focus(), 50);
  }, [annotatingComponentId, annotatingTarget, existing?.text]);

  if (!component || !annotatingComponentId) return null;

  const colors = getTypeColors(component.type, darkMode);
  const meta = TYPE_META[component.type];

  const handleSave = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    addAnnotation(annotatingComponentId, trimmed, targetType, targetId, targetName);
  };

  const handleDelete = () => {
    if (existing) {
      deleteAnnotation(existing.id);
    }
    setAnnotatingComponent(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSave();
    }
    if (e.key === "Escape") {
      setAnnotatingComponent(null);
    }
  };

  const headerLabel = targetType === "component"
    ? component.name
    : targetType === "file"
      ? targetName.split("/").pop() || targetName
      : targetName;

  const headerSubLabel = targetType === "component"
    ? component.docs?.purpose || null
    : targetType === "file"
      ? targetName
      : `Symbol in ${component.name}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={() => setAnnotatingComponent(null)}
      />

      {/* Modal */}
      <div className={`
        relative w-full max-w-md mx-4 rounded-xl border shadow-2xl
        ${darkMode ? "bg-zinc-900 border-zinc-700" : "bg-white border-zinc-200"}
      `}>
        {/* Header */}
        <div className={`px-4 py-3 border-b ${darkMode ? "border-zinc-800" : "border-zinc-100"}`}>
          <div className="flex items-center gap-2">
            {targetType === "component" && meta?.icon && <span>{meta.icon}</span>}
            {targetType === "file" && <span className="text-xs">&#x1F4C4;</span>}
            {targetType === "symbol" && <span className={`text-[10px] font-bold px-1 rounded ${darkMode ? "bg-zinc-700 text-zinc-300" : "bg-zinc-200 text-zinc-600"}`}>S</span>}
            <span className={`font-semibold text-sm ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>
              {headerLabel}
            </span>
            {targetType === "component" && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${colors.badge}`}>
                {meta?.label || component.type}
              </span>
            )}
            {targetType !== "component" && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-500"}`}>
                {targetType}
              </span>
            )}
          </div>
          {headerSubLabel && (
            <p className={`text-[11px] mt-1 truncate ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              {headerSubLabel}
            </p>
          )}
        </div>

        {/* Input */}
        <div className="p-4">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Add your feedback for this ${targetType}...`}
            rows={4}
            className={`
              w-full px-3 py-2 rounded-lg border text-sm resize-none
              ${darkMode
                ? "bg-zinc-800 border-zinc-700 text-zinc-200 placeholder-zinc-600 focus:border-blue-500"
                : "bg-zinc-50 border-zinc-200 text-zinc-800 placeholder-zinc-400 focus:border-blue-400"
              }
              focus:outline-none focus:ring-1 focus:ring-blue-500/50
            `}
          />
          <p className={`text-[10px] mt-1.5 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            {navigator.platform.includes("Mac") ? "\u2318" : "Ctrl"}+Enter to save, Esc to cancel
          </p>
        </div>

        {/* Actions */}
        <div className={`px-4 py-3 border-t flex items-center justify-between ${darkMode ? "border-zinc-800" : "border-zinc-100"}`}>
          <div>
            {existing && (
              <button
                onClick={handleDelete}
                className={`text-xs px-3 py-1.5 rounded-lg ${darkMode ? "text-red-400 hover:bg-red-500/10" : "text-red-500 hover:bg-red-50"}`}
              >
                Remove
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setAnnotatingComponent(null)}
              className={`text-xs px-3 py-1.5 rounded-lg ${darkMode ? "text-zinc-400 hover:bg-zinc-800" : "text-zinc-500 hover:bg-zinc-100"}`}
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={!text.trim()}
              className={`
                text-xs px-4 py-1.5 rounded-lg font-medium
                ${text.trim()
                  ? darkMode
                    ? "bg-blue-600 text-white hover:bg-blue-500"
                    : "bg-blue-500 text-white hover:bg-blue-600"
                  : darkMode
                    ? "bg-zinc-800 text-zinc-600 cursor-not-allowed"
                    : "bg-zinc-100 text-zinc-400 cursor-not-allowed"
                }
              `}
            >
              {existing ? "Update" : "Add"} Feedback
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
