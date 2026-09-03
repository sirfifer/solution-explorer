import { useState, memo, useMemo, useCallback, useEffect } from "react";
import type { Component } from "../types";
import { useArchStore, flattenTopLevel } from "../store";
import { getTypeColors, getLanguageColor, formatNumber, TYPE_META, isHeroType } from "../utils/layout";
import { ChangelogPanel } from "./ChangelogPanel";

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
  onSelect?: () => void;
}

const TreeNode = memo(function TreeNode({ component, depth, expandedIds, onToggleExpand, onSelect }: TreeNodeProps) {
  const { selectedComponentId, selectComponent, drillInto, darkMode, annotations, requestDetailReveal } = useArchStore();
  const hasAnnotation = annotations.some((a) => a.componentId === component.id);
  const expanded = expandedIds.has(component.id);
  const hasChildren = component.children.length > 0;
  const isSelected = selectedComponentId === component.id;
  const colors = getTypeColors(component.type, darkMode);
  const langColor = component.language ? getLanguageColor(component.language) : null;

  return (
    <div>
      {/*
        The identity attributes are the crawler's contract with this tree
        (viewer/tests/crawl/). A scripted walk cannot discover what the data
        says should be here from tailwind classes, so the node publishes its
        own id, depth, and expandability.

        Identity attributes only, and deliberately no role="tree"/"treeitem".
        An earlier revision of this file added them, which was the exact mistake
        DetailPanel refuses a few files away: the ARIA tree pattern is a
        contract, not a label. It obliges roving tabindex, Up/Down between
        visible items, Right to expand, Left to collapse and move to the parent,
        and Home/End. This tree implements none of that. Announcing "tree" and
        then ignoring every key it teaches the reader to press leaves a
        screen-reader user worse off than plain buttons, which at least tab
        predictably. aria-expanded stays, because a disclosure button really
        does expand and that claim is kept.
      */}
      <button
        aria-expanded={hasChildren ? expanded : undefined}
        data-testid="tree-node"
        data-component-id={component.id}
        data-component-type={component.type}
        data-depth={depth}
        data-has-children={hasChildren}
        data-expanded={hasChildren ? expanded : undefined}
        data-selected={isSelected}
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
        // A tree row is a selection made for the reader in the sense the
        // mobile sheet cares about: on a phone the tree is a drawer that covers
        // the canvas, so the reader never sees the node this selects and a
        // peek-height sheet shows them a name they just tapped. Ask for the
        // detail to be revealed; a direct tap on a graph node does not.
        onClick={() => {
          selectComponent(component.id);
          requestDetailReveal();
          onSelect?.();
        }}
        onDoubleClick={() => hasChildren && drillInto(component)}
      >
        {/* Expand/collapse */}
        {hasChildren ? (
          <span
            data-testid="tree-node-toggle"
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
        <div data-testid="tree-children" data-parent-id={component.id}>
          {component.children.map((child) => (
            <TreeNode
              key={child.id}
              component={child}
              depth={depth + 1}
              expandedIds={expandedIds}
              onToggleExpand={onToggleExpand}
              onSelect={onSelect}
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
  onSelect?: () => void;
}

const FolderNode = memo(function FolderNode({
  name,
  children,
  darkMode,
  expandedIds,
  folderExpandedIds,
  onToggleExpand,
  onToggleFolderExpand,
  onSelect,
}: FolderNodeProps) {
  const expanded = folderExpandedIds.has(name);

  return (
    <div>
      <button
        aria-expanded={expanded}
        data-testid="tree-folder"
        data-folder-name={name}
        data-expanded={expanded}
        data-child-count={children.length}
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
        <div data-testid="tree-children" data-folder-name={name}>
          {children.map((child) => (
            <TreeNode
              key={child.id}
              component={child}
              depth={1}
              expandedIds={expandedIds}
              onToggleExpand={onToggleExpand}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
});

/**
 * The chain of ancestor ids above `targetId`, outermost first.
 *
 * Needed because the tree's expansion state is a flat set of ids: revealing a
 * node five levels down means opening every one of its parents, and only the
 * architecture knows who those are.
 */
function ancestorPath(components: Component[], targetId: string): string[] {
  let found: string[] = [];
  const walk = (nodes: Component[], trail: string[]): boolean => {
    for (const node of nodes) {
      if (node.id === targetId) {
        found = trail;
        return true;
      }
      if (node.children?.length && walk(node.children, [...trail, node.id])) return true;
    }
    return false;
  };
  walk(components, []);
  return found;
}

/** Escape a component id for use inside a quoted CSS attribute selector. */
function attrSelectorValue(value: string): string {
  return value.replace(/["\\]/g, "\\$&");
}

export function TreeNavigator({ onSelect }: { onSelect?: () => void } = {}) {
  const { architecture, darkMode } = useArchStore();
  const selectedComponentId = useArchStore((s) => s.selectedComponentId);
  const drillLevel = useArchStore((s) => s.drillLevel);

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

  // Reveal the selected component in the tree, wherever the selection came
  // from: a deep link, the graph, search, a breadcrumb.
  //
  // Before this, arriving at a nested component rendered the right detail panel
  // beside a tree that showed no row for it. The reader had a page with no
  // sense of place: no siblings, no parent, and no way further down without
  // starting the walk again from the top. A shared link is the worst case,
  // because the recipient has none of the context the sender had. Found by the
  // deterministic crawl (viewer/tests/crawl/), which reported every one of 20
  // sampled nested components as unreachable in the navigator.
  //
  // Deliberately one-directional: this opens ancestors on selection, and never
  // closes anything. Collapsing a parent by hand sticks, because expandedIds is
  // not a dependency here, so the reader's own tidying is not undone.
  //
  // The drill level is revealed the same way, and opened, so the tree shows
  // the children the canvas is showing. A level whose row was still collapsed
  // gave the reader a canvas of children beside a tree that named none of
  // them, and left the crawl's drill journey with "neither a graph node nor a
  // tree row" for a component that promotion had lifted off the canvas (VS
  // Code, 2026-09-02, src/vs at the src level).
  useEffect(() => {
    if (!architecture || (!selectedComponentId && !drillLevel)) return;

    const ancestors = [
      ...(selectedComponentId ? ancestorPath(architecture.components, selectedComponentId) : []),
      ...(drillLevel ? [...ancestorPath(architecture.components, drillLevel), drillLevel] : []),
    ];
    if (ancestors.length > 0) {
      setExpandedIds((prev) => {
        const missing = ancestors.filter((id) => !prev.has(id));
        if (missing.length === 0) return prev;
        const next = new Set(prev);
        for (const id of missing) next.add(id);
        return next;
      });
    }

    // A component can also live under an "Internal Components" folder, which is
    // a separate collapsed container keyed by parent NAME rather than by id.
    //
    // The folder may hold an ANCESTOR rather than the component itself.
    // collectOtherComponents adds a component to a group and deliberately does
    // not recurse into its children, so a node five levels down is reached by
    // expanding the grouped ancestor and then walking down inside it. Matching
    // only the selected id left every deep component under extensions/ with no
    // row at all, which is what the crawl caught on private large-repository validation corpus after this fix
    // looked correct on a smaller subject.
    const chain = selectedComponentId ? [...ancestors, selectedComponentId] : ancestors;
    const group = otherGroups.find((g) =>
      g.components.some((c) => chain.includes(c.id)),
    );
    if (group) {
      setFolderExpandedIds((prev) =>
        prev.has(group.parentName) ? prev : new Set(prev).add(group.parentName),
      );
    }
  }, [architecture, selectedComponentId, drillLevel, otherGroups]);

  // Bring the revealed row into view. Separate from the expansion effect so it
  // runs after the newly opened rows have rendered; `block: "nearest"` scrolls
  // the tree's own scroll container and leaves the rest of the page alone.
  useEffect(() => {
    if (!selectedComponentId) return;
    const node = document.querySelector(
      `[data-testid="tree-node"][data-component-id="${attrSelectorValue(selectedComponentId)}"]`,
    );
    node?.scrollIntoView?.({ block: "nearest" });
  }, [selectedComponentId, expandedIds, folderExpandedIds]);

  if (!architecture) return null;

  return (
    <div className="h-full flex flex-col">
      <div className={`px-4 py-3 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        <h2 className={`text-xs font-semibold uppercase tracking-wider ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
          Architecture
        </h2>
      </div>
      <div
        data-testid="tree-navigator"
        className="flex-1 overflow-y-auto py-2"
      >
        {/* Changelog / What's New notifications */}
        <ChangelogPanel />

        {/* Top-level components (main graph items) */}
        {topLevel.map((comp) => (
          <TreeNode
            key={comp.id}
            component={comp}
            depth={0}
            expandedIds={expandedIds}
            onToggleExpand={onToggleExpand}
            onSelect={onSelect}
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
                onSelect={onSelect}
              />
            ))}
          </>
        )}
      </div>

      {/* Version indicator */}
      <div className={`px-4 py-2 border-t text-[10px] ${darkMode ? "border-zinc-800 text-zinc-600" : "border-zinc-200 text-zinc-400"}`}>
        v{__APP_VERSION__}
      </div>
    </div>
  );
}
