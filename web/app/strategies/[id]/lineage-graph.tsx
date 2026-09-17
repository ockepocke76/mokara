"use client";

/** The lineage graph: the strategy's version chain plus the user's own forks
 *  branching off it, drawn with Mermaid (same renderer as the strategy
 *  flowcharts). Plain-language labels per the W5 UX rules — this is the map;
 *  the Versions list below it is where restores happen. */
import { MermaidChart } from "@/components/mermaid-chart";

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
  heads?: { id: number; name: string }[];
};

const SOURCE_LABELS: Record<string, string> = {
  create: "created",
  evolve: "evolved",
  edit: "edited",
  revert: "restored",
  backfill: "imported",
};

/** Mermaid labels break on quotes/brackets and we never want markup from
 *  user text — keep letters, digits and light punctuation only. */
function clean(text: string, max: number): string {
  const stripped = text.replace(/[^\p{L}\p{N} .,%:;!?'()\-–—/]/gu, " ").replace(/\s+/g, " ").trim();
  return stripped.length > max ? `${stripped.slice(0, max - 1)}…` : stripped;
}

export function buildLineageMermaid(
  nodes: LineageNode[],
  currentStrategyName: string,
): string | null {
  if (nodes.length < 2) return null;
  const hasBranching = nodes.some((n) => !n.in_spine || n.inherited);
  if (!hasBranching) return null; // a straight line duplicates the list below

  const ids = new Set(nodes.map((n) => n.id));
  const lines = ["flowchart LR"];
  const oldestFirst = [...nodes].sort((a, b) =>
    (a.created_at ?? "").localeCompare(b.created_at ?? ""),
  );
  for (const n of oldestFirst) {
    const parts: string[] = [];
    if (n.inherited) {
      parts.push("from the original");
    } else {
      parts.push(SOURCE_LABELS[n.source ?? ""] ?? n.source ?? "saved");
    }
    if (n.created_at) parts.push(clean(n.created_at.slice(0, 10), 12));
    if (n.request) parts.push(clean(n.request, 34));
    for (const h of n.heads ?? []) {
      const name = clean(h.name, 24);
      parts.push(
        name === clean(currentStrategyName, 24)
          ? "current version"
          : `current of ${name}`,
      );
    }
    lines.push(`  v${n.id}["${parts.join("<br/>")}"]`);
    const cls = n.inherited ? "inherited" : n.in_spine ? "spine" : "fork";
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
    "  classDef inherited fill:#fef9c3,stroke:#ca8a04,color:#713f12,stroke-dasharray: 4 3",
  );
  return lines.join("\n");
}

export function LineageGraph({
  nodes,
  strategyName,
}: {
  nodes: LineageNode[];
  strategyName: string;
}) {
  const code = buildLineageMermaid(nodes, strategyName);
  if (!code) return null;
  return (
    <div className="space-y-2">
      <p className="text-sm font-semibold">Lineage</p>
      <p className="text-sm text-muted-foreground">
        How this strategy&apos;s code branched over time — blue is this
        strategy&apos;s own line, yellow is what it was cloned from, grey are
        your other strategies that branched off it.
      </p>
      <div className="overflow-x-auto rounded-md border p-3">
        <MermaidChart code={code} />
      </div>
    </div>
  );
}
