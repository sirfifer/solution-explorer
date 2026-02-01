import { useState, memo } from "react";
import type { Component } from "../types";
import { useArchStore } from "../store";
import { getTypeColors, getLanguageColor, formatNumber, TYPE_META, isHeroType } from "../utils/layout";

interface TreeNodeProps {
  component: Component;
  depth: number;
}

const TreeNode = memo(function TreeNode({ component, depth }: TreeNodeProps) {
  const { selectedComponentId, selectComponent, drillInto, darkMode, annotations } = useArchStore();
  const hasAnnotation = annotations.some((a) => a.componentId === component.id);
  const [expanded, setExpanded] = useState(depth < 1);
  const hasChildren = component.children.length > 0;
  const isSelected = selectedComponentId === component.id;
  const colors = getTypeColors(component.type, darkMode);
  const langColor = component.language ? getLanguageColor(component.language) : null;

  return (
    <div>
      <button
        className={`
          w-full text-left flex items-center gap-2 px-3 py-1.5 text-sm
          transition-colors rounded-lg mx-1
          ${isSelected
            ? darkMode
              ? "bg-blue-500/15 text-blue-300"
              : "bg-blue-50 text-blue-700"
            : darkMode
              ? "hover:bg-zinc-800/50 text-zinc-300"
              : "hover:bg-zinc-100 text-zinc-700"
          }
        `}
        style={{ paddingLeft: `${depth * 16 + 12}px` }}
        onClick={() => selectComponent(component.id)}
        onDoubleClick={() => hasChildren && drillInto(component)}
      >
        {/* Expand/collapse */}
        {hasChildren ? (
          <span
            className={`w-4 h-4 flex items-center justify-center text-[10px] shrink-0 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
          >
            {expanded ? "\u25BC" : "\u25B6"}
          </span>
        ) : (
          <span className="w-4 shrink-0" />
        )}

        {/* Language dot */}
        {langColor && (
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ backgroundColor: langColor }}
          />
        )}

        {/* Name */}
        <span className={`truncate flex-1 ${isHeroType(component.type) ? "font-semibold" : "font-medium"}`}>
          {isHeroType(component.type) && TYPE_META[component.type]?.icon && (
            <span className="mr-1">{TYPE_META[component.type].icon}</span>
          )}
          {component.name}
        </span>

        {/* Badge */}
        <span className={`${isHeroType(component.type) ? "text-[10px] px-1.5" : "text-[9px] px-1"} py-0.5 rounded ${colors.badge} shrink-0`}>
          {isHeroType(component.type) ? (TYPE_META[component.type]?.label || component.type) : (TYPE_META[component.type]?.icon || component.type.slice(0, 3))}
        </span>

        {/* Metrics */}
        {component.metrics?.files > 0 && (
          <span className={`text-[10px] tabular-nums shrink-0 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            {formatNumber(component.metrics.files)}
          </span>
        )}

        {/* Annotation indicator */}
        {hasAnnotation && (
          <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" title="Has review annotation" />
        )}
      </button>

      {expanded && hasChildren && (
        <div>
          {component.children.map((child) => (
            <TreeNode
              key={child.id}
              component={child}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
});

export function TreeNavigator() {
  const { architecture, darkMode } = useArchStore();

  if (!architecture) return null;

  return (
    <div className="h-full flex flex-col">
      <div className={`px-4 py-3 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        <h2 className={`text-xs font-semibold uppercase tracking-wider ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
          Components
        </h2>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {architecture.components.map((comp) => (
          <TreeNode key={comp.id} component={comp} depth={0} />
        ))}
      </div>
    </div>
  );
}
