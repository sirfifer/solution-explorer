import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { AggregateNode as AggregateNodeData } from "../types";
import { TYPE_META } from "../utils/layout";
import { useArchStore } from "../store";

interface AggregateNodeProps {
  aggregate: AggregateNodeData;
  [key: string]: unknown;
}

// Renders a collapsed/expanded aggregate of small internal modules (P6-4). It is
// the visible trace that replaces the old silent hero-filter hiding: the node
// names how many members it holds and expands them in place. When expanded it
// stays on screen as a labeled group with a collapse affordance, so the grouping
// never disappears.
export const AggregateNode = memo(function AggregateNode({ data }: NodeProps) {
  const { aggregate } = data as AggregateNodeProps;
  const darkMode = useArchStore((s) => s.darkMode);
  const expanded = useArchStore((s) => !!s.expandedAggregates[aggregate.id]);
  const toggleAggregate = useArchStore((s) => s.toggleAggregate);

  const icon = TYPE_META[aggregate.aggregateType]?.icon ?? "▦"; // ▦
  const typeLabel = TYPE_META[aggregate.aggregateType]?.label ?? aggregate.aggregateType;

  return (
    <div
      className={`
        relative rounded-xl border-2 border-dashed min-w-[220px] max-w-[300px] cursor-pointer
        transition-transform duration-150 hover:scale-[1.02]
        ${darkMode
          ? "border-zinc-600 bg-zinc-900/70 text-zinc-300"
          : "border-zinc-300 bg-zinc-50 text-zinc-700"}
      `}
      onClick={() => toggleAggregate(aggregate.id)}
      title={expanded ? "Collapse this group" : "Expand this group"}
    >
      <Handle id="target-left" type="target" position={Position.Left} className="!bg-zinc-500 !w-2 !h-2 !border-0" />
      <Handle id="target-top" type="target" position={Position.Top} className="!bg-zinc-500 !w-2 !h-2 !border-0" />
      <Handle id="source-right" type="source" position={Position.Right} className="!bg-zinc-500 !w-2 !h-2 !border-0" />
      <Handle id="source-bottom" type="source" position={Position.Bottom} className="!bg-zinc-500 !w-2 !h-2 !border-0" />

      <div className="px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-base shrink-0">{icon}</span>
            <div className="min-w-0">
              <div className={`font-semibold text-sm truncate ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
                {aggregate.memberCount} {typeLabel}
                {aggregate.memberCount !== 1 ? "s" : ""}
              </div>
              <div className={`text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                {expanded ? "Expanded group" : "Grouped to reduce clutter"}
              </div>
            </div>
          </div>
          <button
            className={`
              shrink-0 w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold
              ${darkMode ? "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200" : "bg-zinc-200 text-zinc-600 hover:bg-zinc-300"}
            `}
            onClick={(e) => { e.stopPropagation(); toggleAggregate(aggregate.id); }}
            title={expanded ? "Collapse" : "Expand"}
          >
            {expanded ? "−" : "+"}
          </button>
        </div>

        {/* Member preview so the group is legible without expanding. */}
        <div className={`mt-2 flex flex-wrap gap-1`}>
          {aggregate.members.slice(0, expanded ? 0 : 5).map((m) => (
            <span
              key={m.id}
              className={`text-[9px] px-1.5 py-0.5 rounded truncate max-w-[110px] ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-500"}`}
            >
              {m.name}
            </span>
          ))}
          {!expanded && aggregate.members.length > 5 && (
            <span className={`text-[9px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
              +{aggregate.members.length - 5}
            </span>
          )}
        </div>
      </div>
    </div>
  );
});
