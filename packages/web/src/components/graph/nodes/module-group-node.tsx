"use client";

import { memo, useContext } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Folder, FileText } from "lucide-react";
import { GraphContext } from "../graph-flow";
import type { ModuleNodeData } from "../elk-layout";

const COMMUNITY_COLORS = [
  "#6366f1", "#ec4899", "#10b981", "#f59e0b", "#3b82f6", "#a855f7",
  "#14b8a6", "#f97316", "#84cc16", "#06b6d4", "#e11d48", "#8b5cf6",
  "#22c55e", "#eab308", "#0ea5e9", "#d946ef", "#ef4444", "#78716c",
  "#64748b", "#0891b2", "#059669", "#b45309", "#7c3aed", "#db2777",
];

function docCoverageColor(pct: number): string {
  if (pct >= 0.7) return "var(--color-node-documented)";
  if (pct >= 0.3) return "var(--color-risk-medium)";
  return "var(--color-risk-high)";
}

function ModuleGroupNodeInner({ id, data }: NodeProps) {
  const d = data as ModuleNodeData;
  const ctx = useContext(GraphContext);
  const docPct = d.docCoveragePct ?? 0;

  // Color mode determines the accent/border color
  let accentColor: string;
  switch (ctx.colorMode) {
    case "risk":
      accentColor = docCoverageColor(docPct); // use doc coverage as proxy for module risk
      break;
    case "community": {
      // Use a hash of the module name to pick a community color
      let hash = 0;
      for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) | 0;
      accentColor = COMMUNITY_COLORS[Math.abs(hash) % COMMUNITY_COLORS.length];
      break;
    }
    case "language":
    default:
      accentColor = "var(--color-accent-graph)";
      break;
  }

  const isOnPath = ctx.highlightedPath.has(id);
  const hasActivePath = ctx.highlightedPath.size > 0;
  const isDimmed = hasActivePath && !isOnPath;

  return (
    <div
      className="rounded-xl border-2 bg-[var(--color-bg-elevated)]/80 backdrop-blur-sm px-4 py-3 min-w-[180px] shadow-lg shadow-black/20 transition-all duration-200 cursor-pointer hover:shadow-[0_0_20px_rgba(245,149,32,0.12)]"
      style={{
        borderColor: isOnPath ? "var(--color-accent-graph)" : accentColor,
        borderLeftWidth: 4,
        opacity: isDimmed ? 0.15 : 1,
        animation: isOnPath ? "graph-path-pulse 2s ease-in-out infinite" : undefined,
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2 !h-2 !bg-[var(--color-border-subtle)] !border-none"
      />

      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <div
          className="flex items-center justify-center w-6 h-6 rounded-md"
          style={{ background: `${accentColor}22` }}
        >
          <Folder className="w-3.5 h-3.5" style={{ color: accentColor }} />
        </div>
        <span className="text-sm font-semibold text-[var(--color-text-primary)] truncate max-w-[140px]">
          {d.label}
        </span>
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-3 text-[10px] text-[var(--color-text-tertiary)]">
        <span className="flex items-center gap-1">
          <FileText className="w-3 h-3" />
          {d.fileCount ?? 0} files
        </span>
        {d.symbolCount != null && d.symbolCount > 0 && (
          <span>{d.symbolCount} sym</span>
        )}
      </div>

      {/* Doc coverage bar */}
      {d.docCoveragePct != null && (
        <div className="mt-2">
          <div className="flex items-center justify-between text-[9px] text-[var(--color-text-tertiary)] mb-0.5">
            <span>Docs</span>
            <span>{Math.round(docPct * 100)}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-[var(--color-bg-inset)] overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${Math.max(2, Math.round(docPct * 100))}%`,
                background: docCoverageColor(docPct),
              }}
            />
          </div>
        </div>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2 !h-2 !bg-[var(--color-border-subtle)] !border-none"
      />
    </div>
  );
}

export const ModuleGroupNode = memo(ModuleGroupNodeInner);
