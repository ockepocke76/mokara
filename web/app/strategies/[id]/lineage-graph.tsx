"use client";

/** The lineage graph: the strategy's version chain plus the user's own forks
 *  branching off it, drawn with Mermaid (same renderer as the strategy
 *  flowcharts). Plain-language labels per the W5 UX rules — this is the map;
 *  the Versions list below it is where restores happen. */
import { useMemo } from "react";

import { MermaidChart } from "@/components/mermaid-chart";
import { cleanMermaidLabel as clean } from "@/lib/mermaid-label";
import { VERSION_SOURCE_LABELS } from "@/lib/version-source-labels";

export type LineageNode = {
  id: number;
  short_hash?: string;
  source?: string;
  request?: string | null;
  created_at?: string | null;
  is_head?: boolean;
  in_spine?: boolean;
  parent_version_id?: number | null;
  inherited?: boolean;
  strategy_name?: string | null;
  strategy_deleted?: boolean;
  heads?: { id: number; name: string }[];
};

const MAX_GRAPH_NODES = 80;

export function buildLineageMermaid(
  nodes: LineageNode[],
  currentStrategyId: number,
): string | null {
  if (nodes.length < 2) return null;
  const hasBranching = nodes.some((n) => !n.in_spine || n.inherited);
  if (!hasBranching) return null; // a straight line duplicates the list below

  const ids = new Set(nodes.map((n) => n.id));
  const lines = ["flowchart LR"];
  const oldestFirst = [...nodes].sort((a, b) =>
    (a.created_at ?? "") < (b.created_at ?? "") ? -1 : 1,
  );
  for (const n of oldestFirst) {
    const parts: string[] = [];
    if (n.inherited) {
      parts.push("from the original");
    } else {
      // Name the strategy a fork node lives on — the text cue that keeps the
      // graph readable without relying on color alone.
      if (!n.in_spine && n.strategy_name) parts.push(clean(n.strategy_name, 26));
      parts.push(clean(VERSION_SOURCE_LABELS[n.source ?? ""] ?? n.source ?? "saved", 16));
      if (n.strategy_deleted) parts.push("(deleted strategy)");
    }
    if (n.created_at) parts.push(n.created_at.slice(0, 10));
    if (n.request) parts.push(clean(n.request, 34));
    for (const h of n.heads ?? []) {
      parts.push(
        h.id === currentStrategyId
          ? "current version"
          : `current of ${clean(h.name, 24)}`,
      );
    }
    lines.push(`  v${n.id}["${parts.join("<br/>")}"]`);
    const cls = n.inherited
      ? "inherited"
      : n.strategy_deleted
        ? "trashed"
        : n.in_spine
          ? "spine"
          : "fork";
    lines.push(`  class v${n.id} ${cls}`);
  }
  for (const n of oldestFirst) {
    if (n.parent_version_id && ids.has(n.parent_version_id)) {
      lines.push(`  v${n.parent_version_id} --> v${n.id}`);
    }
  }
  lines.push(
    "  classDef spine fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f",
    "  classDef fork fill:#f4f4f5,stroke:#a1a1aa,color:#3f3f46",
    "  classDef trashed fill:#f4f4f5,stroke:#a1a1aa,color:#71717a,stroke-dasharray: 2 3",
    "  classDef inherited fill:#fef9c3,stroke:#ca8a04,color:#713f12,stroke-dasharray: 4 3",
  );
  return lines.join("\n");
}

export function LineageGraph({
  nodes,
  strategyId,
}: {
  nodes: LineageNode[];
  strategyId: number;
}) {
  const code = useMemo(
    () =>
      nodes.length > MAX_GRAPH_NODES
        ? null
        : buildLineageMermaid(nodes, strategyId),
    [nodes, strategyId],
  );
  const legend = useMemo(() => {
    const parts = ["blue is this strategy's own line of versions"];
    if (nodes.some((n) => n.inherited))
      parts.push("yellow is the version it was cloned from");
    if (nodes.some((n) => !n.in_spine && !n.inherited))
      parts.push(
        "grey are versions saved on your related strategies (each named on its box)",
      );
    return parts.join(", ") + ".";
  }, [nodes]);
  if (nodes.length > MAX_GRAPH_NODES) {
    return (
      <p className="text-sm text-muted-foreground">
        This strategy&apos;s history is too large to draw — the full list is
        below.
      </p>
    );
  }
  if (!code) return null;
  return (
    <div className="space-y-2">
      <p className="text-sm font-semibold">How this strategy branched</p>
      <p className="text-sm text-muted-foreground">{legend}</p>
      <div className="overflow-x-auto rounded-md border p-3">
        <MermaidChart code={code} />
      </div>
    </div>
  );
}
