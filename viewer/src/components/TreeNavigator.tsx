import { useState, memo, useMemo, useCallback, useEffect } from "react";
import type { Component } from "../types";
import { useArchStore, flattenTopLevel } from "../store";
import { getTypeColors, getLanguageColor, formatNumber, TYPE_META, isHeroType } from "../utils/layout";

// Session storage key for expanded nodes
const EXPANDED_KEY = "arch-tree-expanded";

// Get expanded state from session storage
function getExpandedFromSession(): Set<string> {
  try {
    const stored = sessionStorage.getItem(EXPANDED_KEY);
    if (stored) {
      return new Set(JSON.parse(stored));
    }
  } catch {
    // Ignore parse errors
  }
  return new Set();
}

// Save expanded state to session storage
function saveExpandedToSession(expanded: Set<string>) {
  try {
    sessionStorage.setItem(EXPANDED_KEY, JSON.stringify([...expanded]));
  } catch {
    // Ignore storage errors
  }
}

interface TreeNodeProps {
  component: Component;
  depth: number;
  expandedIds: Set<string>;
  onToggleExpand: (id: string) => void;
}

const TreeNode = memo(function TreeNode({ component, depth, expandedIds, onToggleExpand }: TreeNodeProps) {
  const { selectedComponentId, selectComponent, drillInto, darkMode, annotations } = useArchStore();
  const hasAnnotation = annotations.some((a) => a.componentId === component.id);
  const expanded = expandedIds.has(component.id);
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
              onToggleExpand(component.id);
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
              expandedIds={expandedIds}
              onToggleExpand={onToggleExpand}
            />
          ))}
        </div>
      )}
    </div>
  );
});

// Collect components that are NOT top-level but exist in the tree
// Groups them by their immediate parent type/name for organization
function collectOtherComponents(
  components: Component[],
  topLevelIds: Set<string>,
  parentName: string = "Root",
): { parentName: string; components: Component[] }[] {
  const groups: Map<string, Component[]> = new Map();

  function walk(comps: Component[], parent: string) {
    for (const c of comps) {
      if (topLevelIds.has(c.id)) {
        // This is top-level, but its children might not be
        walk(c.children, c.name);
      } else if (c.type !== "project" && c.type !== "repository" && c.type !== "content") {
        // Non-top-level component, group by parent
        if (!groups.has(parent)) {
          groups.set(parent, []);
        }
        groups.get(parent)!.push(c);
      } else if (c.type === "project" || c.type === "repository") {
        // Structural: recurse
        walk(c.children, parent);
      }
    }
  }

  walk(components, parentName);

  return Array.from(groups.entries())
    .map(([parentName, comps]) => ({ parentName, components: comps }))
    .filter((g) => g.components.length > 0);
}

// Session storage key for expanded folders
const FOLDER_EXPANDED_KEY = "arch-folder-expanded";

function getFolderExpandedFromSession(): Set<string> {
  try {
    const stored = sessionStorage.getItem(FOLDER_EXPANDED_KEY);
    if (stored) {
      return new Set(JSON.parse(stored));
    }
  } catch {
    // Ignore parse errors
  }
  return new Set();
}

function saveFolderExpandedToSession(expanded: Set<string>) {
  try {
    sessionStorage.setItem(FOLDER_EXPANDED_KEY, JSON.stringify([...expanded]));
  } catch {
    // Ignore storage errors
  }
}

interface FolderNodeProps {
  name: string;
  children: Component[];
  darkMode: boolean;
  expandedIds: Set<string>;
  folderExpandedIds: Set<string>;
  onToggleExpand: (id: string) => void;
  onToggleFolderExpand: (name: string) => void;
}

const FolderNode = memo(function FolderNode({
  name,
  children,
  darkMode,
  expandedIds,
  folderExpandedIds,
  onToggleExpand,
  onToggleFolderExpand,
}: FolderNodeProps) {
  const expanded = folderExpandedIds.has(name);

  return (
    <div>
      <button
        className={`w-full text-left flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg mx-1 ${darkMode ? "hover:bg-zinc-800/50 text-zinc-400" : "hover:bg-zinc-100 text-zinc-500"}`}
        onClick={() => onToggleFolderExpand(name)}
      >
        <span className={`w-4 h-4 flex items-center justify-center text-[10px] shrink-0 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
          {expanded ? "\u25BC" : "\u25B6"}
        </span>
        <span className="mr-1">{"\uD83D\uDCC1"}</span>
        <span className="truncate flex-1 font-medium">{name}</span>
        <span className={`text-[9px] px-1 py-0.5 rounded ${darkMode ? "bg-zinc-800 text-zinc-500" : "bg-zinc-200 text-zinc-500"} shrink-0`}>
          {children.length}
        </span>
      </button>
      {expanded && (
        <div>
          {children.map((child) => (
            <TreeNode
              key={child.id}
              component={child}
              depth={1}
              expandedIds={expandedIds}
              onToggleExpand={onToggleExpand}
            />
          ))}
        </div>
      )}
    </div>
  );
});

export function TreeNavigator() {
  const { architecture, darkMode } = useArchStore();

  // Tree expansion state - starts collapsed (empty set), restored from session
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => getExpandedFromSession());
  const [folderExpandedIds, setFolderExpandedIds] = useState<Set<string>>(() => getFolderExpandedFromSession());

  // Save to session storage whenever expansion state changes
  useEffect(() => {
    saveExpandedToSession(expandedIds);
  }, [expandedIds]);

  useEffect(() => {
    saveFolderExpandedToSession(folderExpandedIds);
  }, [folderExpandedIds]);

  const onToggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const onToggleFolderExpand = useCallback((name: string) => {
    setFolderExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }, []);

  const { topLevel, otherGroups } = useMemo(() => {
    if (!architecture) return { topLevel: [], otherGroups: [] };

    const topLevel = flattenTopLevel(architecture.components, architecture.relationships);
    const topLevelIds = new Set(topLevel.map((c) => c.id));
    const otherGroups = collectOtherComponents(architecture.components, topLevelIds);

    return { topLevel, otherGroups };
  }, [architecture]);

  if (!architecture) return null;

  return (
    <div className="h-full flex flex-col">
      <div className={`px-4 py-3 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        <h2 className={`text-xs font-semibold uppercase tracking-wider ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
          Architecture
        </h2>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {/* Top-level components (main graph items) */}
        {topLevel.map((comp) => (
          <TreeNode
            key={comp.id}
            component={comp}
            depth={0}
            expandedIds={expandedIds}
            onToggleExpand={onToggleExpand}
          />
        ))}

        {/* Other components grouped by parent */}
        {otherGroups.length > 0 && (
          <>
            <div className={`px-4 py-2 mt-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
              <h3 className={`text-[10px] font-semibold uppercase tracking-wider ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                Internal Components
              </h3>
            </div>
            {otherGroups.map((group) => (
              <FolderNode
                key={group.parentName}
                name={group.parentName}
                children={group.components}
                darkMode={darkMode}
                expandedIds={expandedIds}
                folderExpandedIds={folderExpandedIds}
                onToggleExpand={onToggleExpand}
                onToggleFolderExpand={onToggleFolderExpand}
              />
            ))}
          </>
        )}
      </div>
    </div>
  );
}
