"use client";

import { LANGUAGE_COLORS } from "@/lib/utils/confidence";
import type { ColorMode, ViewMode } from "./graph-toolbar";

const COMMUNITY_SAMPLE = [
  { color: "#6366f1", label: "Community 1" },
  { color: "#ec4899", label: "Community 2" },
  { color: "#10b981", label: "Community 3" },
  { color: "#f59e0b", label: "Community 4" },
  { color: "#3b82f6", label: "Community 5" },
  { color: "#a855f7", label: "Community 6" },
];

const LANGUAGE_LEGEND = [
  { lang: "python", color: LANGUAGE_COLORS.python, label: "Python" },
  { lang: "typescript", color: LANGUAGE_COLORS.typescript, label: "TypeScript" },
  { lang: "go", color: LANGUAGE_COLORS.go, label: "Go" },
  { lang: "rust", color: LANGUAGE_COLORS.rust, label: "Rust" },
  { lang: "java", color: LANGUAGE_COLORS.java, label: "Java" },
  { lang: "config", color: LANGUAGE_COLORS.config, label: "Config" },
  { lang: "other", color: LANGUAGE_COLORS.other, label: "Other" },
];

interface GraphLegendProps {
  nodeCount: number;
  edgeCount: number;
  colorMode: ColorMode;
  viewMode: ViewMode;
}

export function GraphLegend({
  nodeCount,
  edgeCount,
  colorMode,
  viewMode,
}: GraphLegendProps) {
  return (
    <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-overlay)]/80 backdrop-blur-sm p-2.5 text-xs space-y-1.5 min-w-[130px] max-w-[160px] shadow-lg shadow-black/20">
      <div className="font-medium text-[var(--color-text-secondary)] tabular-nums">
        {nodeCount} nodes &middot; {edgeCount} edges
      </div>

      <div className="border-t border-[var(--color-border-default)] pt-1.5 space-y-1">
        {/* Doc status — always shown */}
        <div className="flex items-center gap-2 text-[var(--color-text-tertiary)]">
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ background: "var(--color-node-documented)" }}
          />
          <span>Has docs</span>
        </div>
        <div className="flex items-center gap-2 text-[var(--color-text-tertiary)]">
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ background: "var(--color-node-undocumented)" }}
          />
          <span>No docs</span>
        </div>
      </div>

      {/* Color mode legend */}
      <div className="border-t border-[var(--color-border-default)] pt-1.5 space-y-1">
        <p className="text-[9px] text-[var(--color-text-tertiary)] uppercase tracking-wider font-medium mb-1">
          {colorMode === "language" ? "Language" : colorMode === "community" ? "Community" : "Risk"}
        </p>

        {colorMode === "language" &&
          LANGUAGE_LEGEND.map((l) => (
            <div key={l.lang} className="flex items-center gap-2 text-[var(--color-text-tertiary)]">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ background: l.color }}
              />
              <span>{l.label}</span>
            </div>
          ))}

        {colorMode === "community" &&
          COMMUNITY_SAMPLE.map((c, i) => (
            <div key={i} className="flex items-center gap-2 text-[var(--color-text-tertiary)]">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ background: c.color }}
              />
              <span>{c.label}</span>
            </div>
          ))}

        {colorMode === "risk" && (
          <>
            <div className="flex items-center gap-2 text-[var(--color-text-tertiary)]">
              <span className="w-2 h-2 rounded-full shrink-0 bg-[#22c55e]" />
              <span>Low risk</span>
            </div>
            <div className="flex items-center gap-2 text-[var(--color-text-tertiary)]">
              <span className="w-2 h-2 rounded-full shrink-0 bg-[#f59520]" />
              <span>Medium risk</span>
            </div>
            <div className="flex items-center gap-2 text-[var(--color-text-tertiary)]">
              <span className="w-2 h-2 rounded-full shrink-0 bg-[#ef4444]" />
              <span>High risk</span>
            </div>
          </>
        )}
      </div>

      {/* View-specific info */}
      {viewMode !== "module" && viewMode !== "full" && (
        <div className="border-t border-[var(--color-border-default)] pt-1.5">
          <p className="text-[9px] text-[var(--color-text-tertiary)]">
            {viewMode === "dead" && "Showing unreachable files"}
            {viewMode === "hotfiles" && "Most-committed files (30d)"}
            {viewMode === "architecture" && "Entry-point reachable (3 hops)"}
          </p>
        </div>
      )}

      <p className="text-[9px] text-[var(--color-text-tertiary)] pt-1 border-t border-[var(--color-border-default)]">
        Click &middot; Double-click &middot; Right-click
      </p>
    </div>
  );
}
