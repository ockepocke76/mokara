"use client";

/** The strategy family tree: how this strategy relates to the strategies it
 *  was cloned from and the ones cloned from it, across users. Strategy-level
 *  only — code history lives in the History tab. Only public/published,
 *  built-in, and the viewer's own strategies appear; everything else shows as
 *  an anonymous hidden-forks count. */
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { MermaidChart } from "@/components/mermaid-chart";
import { cleanMermaidLabel as clean } from "@/lib/mermaid-label";

type FamilyNode = {
  id: number;
  parent_id: number | null;
  name: string;
  owner: string;
  is_builtin: boolean;
  is_own: boolean;
  is_private: boolean;
  is_deleted: boolean;
  is_self: boolean;
  score: number | null;
  hidden_forks: number;
};

const MAX_TREE_NODES = 60;

export function buildFamilyMermaid(nodes: FamilyNode[]): string | null {
  if (nodes.length < 2) return null;
  const ids = new Set(nodes.map((n) => n.id));
  const lines = ["flowchart TD"];
  for (const n of nodes) {
    const parts = [clean(n.name, 28)];
    if (n.is_builtin) parts.push("built-in");
    else if (!n.is_self) parts.push(`by ${clean(n.owner, 20)}`);
    if (n.is_deleted) parts.push("(deleted)");
    if (n.score != null) parts.push(`Excellence ${n.score.toFixed(1)}`);
    if (n.is_self) parts.push("this strategy");
    if (n.is_private && !n.is_deleted) parts.push("(private — only you see it)");
    if (n.hidden_forks > 0)
      parts.push(`+${n.hidden_forks} private fork${n.hidden_forks === 1 ? "" : "s"}`);
    lines.push(`  s${n.id}["${parts.join("<br/>")}"]`);
    const cls = n.is_deleted
      ? "trashed"
      : n.is_self
        ? "self"
        : n.is_builtin
          ? "builtin"
          : "other";
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
    "  classDef trashed fill:#f4f4f5,stroke:#a1a1aa,color:#71717a,stroke-dasharray: 2 3",
  );
  return lines.join("\n");
}

export function FamilyTree({
  strategyId,
  mayHaveFamily,
}: {
  strategyId: number;
  /** Cheap pre-check from the strategy row (parent pointer / fork counts /
   *  built-in) — most strategies provably have no family, so don't even
   *  fetch for them. Over-inclusive is fine; under-inclusive is not. */
  mayHaveFamily: boolean;
}) {
  const [nodes, setNodes] = useState<FamilyNode[]>([]);
  const [truncated, setTruncated] = useState(false);

  useEffect(() => {
    if (!mayHaveFamily) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/bff/strategies/${strategyId}/family`);
        if (!res.ok) return;
        const body = await res.json();
        if (!cancelled) {
          setNodes(body.nodes ?? []);
          setTruncated(Boolean(body.truncated));
        }
      } catch {
        // No section; a reload recovers.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [strategyId, mayHaveFamily]);

  const code = useMemo(
    () => (nodes.length > MAX_TREE_NODES ? null : buildFamilyMermaid(nodes)),
    [nodes],
  );
  const legend = useMemo(() => {
    const parts = ["blue is this strategy"];
    if (nodes.some((n) => n.is_builtin)) parts.push("purple a built-in");
    if (nodes.some((n) => !n.is_builtin && !n.is_self))
      parts.push("grey other strategies");
    let text = parts.join(", ");
    if (nodes.some((n) => n.hidden_forks > 0))
      text +=
        "; private forks are counted but never named, and anything built on them stays hidden";
    return text + ".";
  }, [nodes]);

  if (nodes.length < 2) return null;

  return (
    <div className="space-y-2">
      <p className="text-sm font-semibold">Family tree</p>
      <p className="text-sm text-muted-foreground">
        Where this strategy came from and what has been built on it. {legend}
      </p>
      {code ? (
        <>
          <div className="overflow-x-auto rounded-md border p-3">
            <MermaidChart code={code} />
          </div>
          <p className="flex flex-wrap gap-2 text-xs">
            {nodes
              .filter((n) => !n.is_self && !n.is_deleted)
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
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          This family is too large to draw
          {truncated ? " (showing nothing rather than a partial tree)" : ""}.
        </p>
      )}
    </div>
  );
}
