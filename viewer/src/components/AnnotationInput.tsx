import { useState, useEffect, useRef } from "react";
import { useArchStore } from "../store";
import { getTypeColors, TYPE_META } from "../utils/layout";

// Human-readable labels for sub-component target types
const TARGET_LABELS: Record<string, string> = {
  "component-name": "name",
  "component-type": "type",
  "component-framework": "framework",
  "component-port": "port",
  "component-purpose": "purpose",
  "component-pattern": "pattern",
};

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
  const targetContext = annotatingTarget?.targetContext;

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
    addAnnotation(annotatingComponentId, trimmed, targetType, targetId, targetName, targetContext);
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

  // Compute header label based on target type
  const headerLabel = (() => {
    switch (targetType) {
      case "component": return component.name;
      case "component-name": return `Name: "${component.name}"`;
      case "component-type": return `Type: ${TYPE_META[component.type]?.label || component.type}`;
      case "component-framework": return `Framework: ${component.framework}`;
      case "component-port": return `Port: :${component.port}`;
      case "component-purpose": return "Purpose Statement";
      case "component-pattern": return `Pattern: ${targetContext?.patternValue || targetName}`;
      case "file": return targetName.split("/").pop() || targetName;
      case "symbol": return targetName;
      default: return targetName;
    }
  })();

  // Compute sub-label with context
  const headerSubLabel = (() => {
    switch (targetType) {
      case "component": return component.docs?.purpose || null;
      case "component-name": return `in ${component.name} (${component.path})`;
      case "component-type": return `Current type: ${component.type}`;
      case "component-framework": return `in ${component.name}`;
      case "component-port": return `in ${component.name}`;
      case "component-purpose": return component.docs?.purpose || "(no purpose set)";
      case "component-pattern": return `in ${component.name}`;
      case "file": return targetName;
      case "symbol": return `Symbol in ${component.name}`;
      default: return null;
    }
  })();

  // Compute icon for the header
  const targetIcon = (() => {
    switch (targetType) {
      case "component": return meta?.icon || null;
      case "component-name": return "Aa";
      case "component-type": return meta?.icon || null;
      case "component-framework": return "\u2699";
      case "component-port": return "\uD83D\uDD0C";
      case "component-purpose": return "\uD83D\uDCDD";
      case "component-pattern": return "\u2B22";
      case "file": return "\uD83D\uDCC4";
      case "symbol": return null;
      default: return null;
    }
  })();

  // Compute placeholder text
  const placeholder = (() => {
    switch (targetType) {
      case "component-name": return "e.g., Rename this to 'AuthService'...";
      case "component-type": return "e.g., This should be classified as a 'service' instead...";
      case "component-framework": return "e.g., This is actually using Fastify, not Express...";
      case "component-port": return "e.g., Port should be 8080 in production...";
      case "component-purpose": return "e.g., The purpose should mention authentication...";
      case "component-pattern": return "e.g., This pattern is incorrect, it's actually Observer...";
      default: return `Add your feedback for this ${targetType}...`;
    }
  })();

  // Determine badge content
  const isSubComponent = targetType.startsWith("component-");
  const badgeLabel = isSubComponent
    ? TARGET_LABELS[targetType] || targetType.replace("component-", "")
    : targetType === "component"
      ? meta?.label || component.type
      : targetType;

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
            {targetIcon && (
              targetType === "symbol" ? (
                <span className={`text-[10px] font-bold px-1 rounded ${darkMode ? "bg-zinc-700 text-zinc-300" : "bg-zinc-200 text-zinc-600"}`}>S</span>
              ) : (
                <span className="text-xs">{targetIcon}</span>
              )
            )}
            {targetType === "symbol" && !targetIcon && (
              <span className={`text-[10px] font-bold px-1 rounded ${darkMode ? "bg-zinc-700 text-zinc-300" : "bg-zinc-200 text-zinc-600"}`}>S</span>
            )}
            <span className={`font-semibold text-sm ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>
              {headerLabel}
            </span>
            {targetType === "component" ? (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${colors.badge}`}>
                {meta?.label || component.type}
              </span>
            ) : (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                isSubComponent
                  ? darkMode ? "bg-blue-900/40 text-blue-300" : "bg-blue-100 text-blue-600"
                  : darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-500"
              }`}>
                {badgeLabel}
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
            placeholder={placeholder}
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
