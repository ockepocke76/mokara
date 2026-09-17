"use client";

/** The strategy family tree: how this strategy relates to the strategies it
 *  was cloned from and the ones cloned from it, across users. Strategy-level
 *  only — code history lives in the History tab. Only public, built-in, and
 *  the viewer's own strategies appear; everything else shows as an anonymous
 *  hidden-forks count. */
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { MermaidChart } from "@/components/mermaid-chart";

type FamilyNode = {
  id: number;
  parent_id: number | null;
  name: string;
  owner: string;
  is_builtin: boolean;
  is_own: boolean;
  is_private: boolean;
  is_self: boolean;
  score: number | null;
  hidden_forks: number;
  created_at: string | null;
};

/** Mermaid flowchart labels break on quotes/brackets — keep letters, digits
 *  and light punctuation (XSS is handled by MermaidChart's pinned
 *  securityLevel "strict"; this is parser-escaping). */
function clean(text: string, max: number): string {
  const stripped = text.replace(/[^\p{L}\p{N} .,%:;!?'()\-–—/]/gu, " ").replace(/\s+/g, " ").trim();
  return stripped.length > max ? `${stripped.slice(0, max - 1)}…` : stripped;
}

const MAX_TREE_NODES = 60;

export function buildFamilyMermaid(nodes: FamilyNode[]): string | null {
  if (nodes.length < 2) return null;
  const ids = new Set(nodes.map((n) => n.id));
  const lines = ["flowchart TD"];
  for (const n of nodes) {
    const parts = [clean(n.name, 28)];
    if (!n.is_builtin && !n.is_self) parts.push(`by ${clean(n.owner, 20)}`);
    if (n.score != null) parts.push(`Excellence ${n.score.toFixed(1)}`);
    if (n.is_self) parts.push("this strategy");
    if (n.is_private) parts.push("(private — only you see it)");
    if (n.hidden_forks > 0)
      parts.push(`+${n.hidden_forks} private fork${n.hidden_forks === 1 ? "" : "s"}`);
    lines.push(`  s${n.id}["${parts.join("<br/>")}"]`);
    const cls = n.is_self ? "self" : n.is_builtin ? "builtin" : "other";
    lines.push(`  class s${n.id} ${cls}`);
  }
  for (const n of nodes) {
    if (n.parent_id && ids.has(n.parent_id)) {
      lines.push(`  s${n.parent_id} --> s${n.id}`);
    }
  }
  lines.push(
    "  classDef self fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f",
    "  classDef builtin fill:#ede9fe,stroke:#8b5cf6,color:#3b0764",
    "  classDef other fill:#f4f4f5,stroke:#a1a1aa,color:#3f3f46",
  );
  return lines.join("\n");
}

export function FamilyTree({ strategyId }: { strategyId: number }) {
  const [nodes, setNodes] = useState<FamilyNode[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/bff/strategies/${strategyId}/family`);
        if (!res.ok) return;
        const body = await res.json();
        if (!cancelled) setNodes(body.nodes ?? []);
      } catch {
        // No section; a reload recovers.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [strategyId]);

  const code = useMemo(
    () =>
      nodes.length > MAX_TREE_NODES ? null : buildFamilyMermaid(nodes),
    [nodes],
  );
  const totalHidden = nodes.reduce((sum, n) => sum + (n.hidden_forks || 0), 0);

  if (nodes.length < 2) return null;

  return (
    <div className="space-y-2">
      <p className="text-sm font-semibold">Family tree</p>
      <p className="text-sm text-muted-foreground">
        Where this strategy came from and what has been built on it. Blue is
        this strategy{nodes.some((n) => n.is_builtin) ? ", purple a built-in" : ""}
        {nodes.some((n) => !n.is_builtin && !n.is_self) ? ", grey other strategies" : ""}
        {totalHidden > 0 ? "; private forks are counted but never named" : ""}.
      </p>
      {code ? (
        <div className="overflow-x-auto rounded-md border p-3">
          <MermaidChart code={code} />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          This family is too large to draw ({nodes.length} strategies).
        </p>
      )}
      <p className="flex flex-wrap gap-2 text-xs">
        {nodes
          .filter((n) => !n.is_self)
          .map((n) => (
            <Link
              key={n.id}
              href={`/strategies/${n.id}`}
              className="rounded-full border px-2 py-0.5 text-muted-foreground hover:bg-muted"
            >
              {n.name}
            </Link>
          ))}
      </p>
    </div>
  );
}
