import { useState, useEffect, useRef } from "react";
import { useArchStore } from "../store";
import { getTypeColors, TYPE_META } from "../utils/layout";

export function AnnotationInput() {
  const {
    annotatingComponentId,
    annotations,
    darkMode,
    setAnnotatingComponent,
    addAnnotation,
    deleteAnnotation,
    getComponentById,
  } = useArchStore();

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const component = annotatingComponentId ? getComponentById(annotatingComponentId) : null;
  const existing = annotations.find((a) => a.componentId === annotatingComponentId);
  const [text, setText] = useState("");

  // Reset text when component changes
  useEffect(() => {
    setText(existing?.text || "");
    // Focus the textarea after a short delay (allows modal to render)
    setTimeout(() => textareaRef.current?.focus(), 50);
  }, [annotatingComponentId, existing?.text]);

  if (!component || !annotatingComponentId) return null;

  const colors = getTypeColors(component.type, darkMode);
  const meta = TYPE_META[component.type];

  const handleSave = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    addAnnotation(annotatingComponentId, trimmed);
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
            {meta?.icon && <span>{meta.icon}</span>}
            <span className={`font-semibold text-sm ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>
              {component.name}
            </span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${colors.badge}`}>
              {meta?.label || component.type}
            </span>
          </div>
          {component.docs?.purpose && (
            <p className={`text-[11px] mt-1 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              {component.docs.purpose}
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
            placeholder="Add your feedback for this component..."
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
