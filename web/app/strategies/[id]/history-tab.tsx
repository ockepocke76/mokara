"use client";

/** History tab: the strategy's evolution timeline (old History tab) —
 *  one entry per evolve/refine request, newest first, genesis at the end. */
import { useEffect, useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

type HistoryEntry = {
  timestamp?: string;
  request?: string;
  commit_sha?: string;
};
type HistoryPayload = {
  history: HistoryEntry[];
  genesis?: string | null;
  created_at?: string | null;
};

function formatTime(value?: string | null): string | null {
  if (!value) return null;
  return value.slice(0, 16).replace("T", " ");
}

export function HistoryTab({ strategyId }: { strategyId: number }) {
  const [payload, setPayload] = useState<HistoryPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/bff/strategies/${strategyId}/history`);
        if (!res.ok) return;
        const body = (await res.json()) as HistoryPayload;
        if (!cancelled) setPayload(body);
      } catch {
        // Leave the skeleton; a reload recovers.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [strategyId]);

  if (!payload) {
    return <Skeleton className="h-40 w-full" />;
  }

  const entries = [...(payload.history ?? [])].reverse(); // newest first

  return (
    <div className="space-y-4">
      {entries.length === 0 && (
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground">
            No evolutions yet — every time you evolve this strategy, the
            request lands here as a timeline entry.
          </CardContent>
        </Card>
      )}

      {entries.map((entry, i) => (
        <div key={i} className="border-l-2 pl-4">
          <p className="text-sm font-semibold">
            Evolution #{entries.length - i}
            <span className="ml-2 font-normal text-muted-foreground">
              {formatTime(entry.timestamp) ?? "unknown time"}
            </span>
            {entry.commit_sha && (
              <span className="ml-2 font-mono text-xs font-normal text-muted-foreground">
                {entry.commit_sha.slice(0, 8)}
              </span>
            )}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {entry.request || "No description"}
          </p>
        </div>
      ))}

      {payload.genesis && (
        <div className="border-l-2 pl-4">
          <p className="text-sm font-semibold">
            🌱 Genesis — original request
            {formatTime(payload.created_at) && (
              <span className="ml-2 font-normal text-muted-foreground">
                {formatTime(payload.created_at)}
              </span>
            )}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {payload.genesis}
          </p>
        </div>
      )}
    </div>
  );
}
