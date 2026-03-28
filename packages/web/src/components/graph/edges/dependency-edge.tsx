"use client";

import { memo, useContext } from "react";
import {
  getSmoothStepPath,
  EdgeLabelRenderer,
  type EdgeProps,
} from "@xyflow/react";
import { GraphContext } from "../graph-flow";
import type { DependencyEdgeData } from "../elk-layout";

function DependencyEdgeInner({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps) {
  const d = (data ?? { importedNames: [], edgeCount: 1 }) as DependencyEdgeData;
  const ctx = useContext(GraphContext);

  const edgeKey = id;
  const isOnPath = ctx.highlightedEdges.has(edgeKey);
  const hasActivePath = ctx.highlightedPath.size > 0;
  const isDimmed = hasActivePath && !isOnPath;
  const isDynamic = d.importedNames.length === 0;

  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 12,
  });

  const strokeWidth = Math.max(1, Math.min(4, 1 + Math.sqrt(d.edgeCount) * 0.5));

  let stroke: string;
  let opacity: number;
  let dashArray: string | undefined;
  let animation: string | undefined;

  if (isOnPath) {
    stroke = "var(--color-accent-graph)";
    opacity = 1;
    dashArray = "6 4";
    animation = "graph-marching-ants 0.6s linear infinite";
  } else if (isDimmed) {
    stroke = "rgba(91, 156, 246, 0.15)";
    opacity = 0.3;
  } else if (isDynamic) {
    stroke = "rgba(150, 150, 150, 0.5)";
    opacity = 0.4;
    dashArray = "4 4";
  } else {
    stroke = "rgba(91, 156, 246, 0.35)";
    opacity = 0.6;
  }

  return (
    <>
      <path
        d={edgePath}
        fill="none"
        stroke={stroke}
        strokeWidth={strokeWidth}
        strokeOpacity={opacity}
        strokeDasharray={dashArray}
        style={{ animation }}
        className="transition-all duration-300"
      />
      {d.edgeCount > 1 && !isDimmed && (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan pointer-events-none absolute rounded-full bg-[var(--color-bg-elevated)] border border-[var(--color-border-default)] px-1.5 py-0.5 text-[9px] font-medium text-[var(--color-text-tertiary)] tabular-nums"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              opacity: isDimmed ? 0.15 : 0.8,
            }}
          >
            {d.edgeCount}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const DependencyEdge = memo(DependencyEdgeInner);
