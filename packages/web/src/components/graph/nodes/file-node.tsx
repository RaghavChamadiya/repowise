"use client";

import { memo, useContext } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { GraphContext } from "../graph-flow";
import { languageColor } from "@/lib/utils/confidence";
import type { FileNodeData } from "../elk-layout";

const COMMUNITY_COLORS = [
  "#6366f1", "#ec4899", "#10b981", "#f59e0b", "#3b82f6", "#a855f7",
  "#14b8a6", "#f97316", "#84cc16", "#06b6d4", "#e11d48", "#8b5cf6",
  "#22c55e", "#eab308", "#0ea5e9", "#d946ef", "#ef4444", "#78716c",
  "#64748b", "#0891b2", "#059669", "#b45309", "#7c3aed", "#db2777",
];

function riskColor(score: number): string {
  if (score <= 0.3) return "#22c55e";
  if (score <= 0.7) return "#f59520";
  return "#ef4444";
}

function FileNodeInner({ id, data }: NodeProps) {
  const d = data as FileNodeData;
  const ctx = useContext(GraphContext);

  const isOnPath = ctx.highlightedPath.has(id);
  const hasActivePath = ctx.highlightedPath.size > 0;
  const isDimmed = hasActivePath && !isOnPath;

  // Determine node accent color based on color mode
  let accentColor: string;
  switch (ctx.colorMode) {
    case "risk": {
      const score = ctx.riskScores.get(d.fullPath) ?? (d.pagerank * 3); // use pagerank as fallback proxy
      accentColor = riskColor(Math.min(1, score));
      break;
    }
    case "community":
      accentColor = COMMUNITY_COLORS[d.communityId % COMMUNITY_COLORS.length];
      break;
    case "language":
    default:
      accentColor = languageColor(d.language);
      break;
  }

  return (
    <div
      className="group relative rounded-lg border transition-all duration-200 cursor-pointer"
      style={{
        borderColor: isOnPath ? "var(--color-accent-graph)" : `${accentColor}60`,
        background: `linear-gradient(135deg, ${accentColor}12 0%, var(--color-bg-surface) 70%)`,
        opacity: isDimmed ? 0.15 : 1,
        animation: isOnPath ? "graph-path-pulse 2s ease-in-out infinite" : undefined,
        borderStyle: d.isTest ? "dashed" : "solid",
        boxShadow: isOnPath
          ? `0 0 16px ${accentColor}40`
          : `0 2px 8px rgba(0,0,0,0.2)`,
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-1.5 !h-1.5 !bg-[var(--color-border-subtle)] !border-none"
      />

      {/* Left accent bar */}
      <div
        className="absolute left-0 top-0 bottom-0 w-[3px] rounded-l-lg"
        style={{ background: accentColor }}
      />

      <div className="flex items-center gap-2 px-3 py-2 pl-3.5">
        {/* Doc status dot */}
        <div
          className="w-2 h-2 rounded-full shrink-0 ring-1 ring-black/10"
          style={{
            background: d.hasDoc
              ? "var(--color-node-documented)"
              : "var(--color-node-undocumented)",
          }}
          title={d.hasDoc ? "Has documentation" : "No documentation"}
        />

        {/* Label */}
        <span className="text-xs font-mono text-[var(--color-text-primary)] truncate max-w-[110px]">
          {d.label}
        </span>

        {/* Entry point badge */}
        {d.isEntryPoint && (
          <span className="shrink-0 text-[8px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-[var(--color-accent-graph)]/15 text-[var(--color-accent-graph)]">
            EP
          </span>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-1.5 !h-1.5 !bg-[var(--color-border-subtle)] !border-none"
      />
    </div>
  );
}

export const FileNode = memo(FileNodeInner);
