"use client";

/** History tab: the strategy's human-input timeline. For the owner this is
 *  built from the generation runs — the verbatim original request, evolve
 *  requests, clarify answers, and refine feedback — plus the version chain
 *  (V39 DAG) with one-click restore. Strategies without recorded runs
 *  (non-owners, migrated rows) fall back to the legacy evolution entries +
 *  genesis. */
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

type RunInput = {
  kind?: string;
  action?: string;
  feedback?: string;
  answers?: Record<string, string>;
  timestamp?: string;
};
type RunEntry = {
  run_id: string;
  kind: "create" | "evolve";
  status: string;
  request?: string | null;
  created_at?: string;
  inputs: RunInput[];
};
type HistoryEntry = {
  timestamp?: string;
  request?: string;
  commit_sha?: string;
};
type HistoryPayload = {
  history: HistoryEntry[];
  runs?: RunEntry[];
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

  const runs = payload.runs ?? [];
  return (
    <div className="space-y-8">
      {runs.length > 0 ? (
        <RunTimeline runs={runs} />
      ) : (
        <LegacyTimeline payload={payload} />
      )}
      <VersionsSection strategyId={strategyId} />
    </div>
  );
}

type VersionEntry = {
  id: number;
  short_hash?: string;
  source?: string;
  request?: string | null;
  created_at?: string | null;
  is_head?: boolean;
  inherited?: boolean;
  from_strategy_id?: number | null;
};

const VERSION_SOURCE_LABELS: Record<string, string> = {
  create: "created",
  evolve: "evolved",
  edit: "edited",
  revert: "restored",
  backfill: "imported",
};

/** The version chain (owner only — the endpoint 404s for everyone else,
 *  which simply hides the section). */
function VersionsSection({ strategyId }: { strategyId: number }) {
  const router = useRouter();
  const [versions, setVersions] = useState<VersionEntry[] | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/bff/strategies/${strategyId}/versions`);
        if (!res.ok) return; // non-owner: no section
        const body = await res.json();
        if (!cancelled) setVersions(body.versions ?? []);
      } catch {
        // Leave hidden; a reload recovers.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [strategyId, refreshKey]);

  async function restore(versionId: number) {
    setBusyId(versionId);
    setError(null);
    try {
      const res = await fetch(`/api/bff/strategies/${strategyId}/revert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version_id: versionId }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(typeof body.detail === "string" ? body.detail : "Restore failed.");
        return;
      }
      setRefreshKey((k) => k + 1); // reload the list
      router.refresh(); // code/params on the page reflect the restored head
    } finally {
      setBusyId(null);
      setConfirmId(null);
    }
  }

  if (!versions || versions.length === 0) return null;

  return (
    <div className="space-y-3">
      <p className="text-sm font-semibold">Versions</p>
      <p className="text-sm text-muted-foreground">
        This strategy&apos;s line of saved code states, newest first (saves
        that changed nothing aren&apos;t repeated). Restoring never deletes
        anything — the restored state becomes a new version.
      </p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="space-y-2">
        {versions.map((v, i) => (
          <div
            key={v.id}
            className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-sm"
          >
            <span className="font-mono text-xs text-muted-foreground">
              v{versions.length - i}
            </span>
            <Badge variant={v.is_head ? "secondary" : "outline"}>
              {v.is_head ? "current" : VERSION_SOURCE_LABELS[v.source ?? ""] ?? v.source}
            </Badge>
            {v.inherited && (
              <Badge variant="outline" title="Saved on the strategy this one was cloned from">
                from the original
              </Badge>
            )}
            {v.short_hash && (
              <span
                className="font-mono text-xs text-muted-foreground"
                title="Content fingerprint — two versions with the same code and parameters share it"
              >
                {v.short_hash}
              </span>
            )}
            <span className="text-xs text-muted-foreground">
              {formatTime(v.created_at)}
            </span>
            <span className="min-w-0 flex-1 truncate text-muted-foreground">
              {v.request ?? ""}
            </span>
            {!v.is_head &&
              (confirmId === v.id ? (
                <Button
                  size="sm"
                  disabled={busyId !== null}
                  onClick={() => restore(v.id)}
                >
                  {busyId === v.id ? "Restoring…" : "Restore this version?"}
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busyId !== null}
                  onClick={() => setConfirmId(v.id)}
                >
                  Restore
                </Button>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function RunTimeline({ runs }: { runs: RunEntry[] }) {
  const newestFirst = [...runs].reverse();
  return (
    <div className="space-y-5">
      <p className="text-sm text-muted-foreground">
        Everything you told the designer about this strategy, verbatim —
        newest first.
      </p>
      {newestFirst.map((run, i) => (
        <div key={run.run_id} className="border-l-2 pl-4">
          <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            {run.kind === "create"
              ? "🌱 Original request"
              : `Evolve request #${runs.filter((r) => r.kind === "evolve").indexOf(run) + 1}`}
            <span className="font-normal text-muted-foreground">
              {formatTime(run.created_at)}
            </span>
            {run.status === "failed" && (
              <Badge variant="destructive">run failed — draft saved</Badge>
            )}
            {i === 0 && run.status === "running" && (
              <Badge variant="outline">running</Badge>
            )}
          </p>
          {run.request && (
            <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">
              {run.request}
            </p>
          )}
          {run.inputs.map((input, j) => (
            <RunInputBlock key={j} input={input} />
          ))}
        </div>
      ))}
    </div>
  );
}

function RunInputBlock({ input }: { input: RunInput }) {
  const time = formatTime(input.timestamp);
  if (input.answers && Object.keys(input.answers).length > 0) {
    return (
      <div className="mt-2 border-l pl-3">
        <p className="text-xs font-medium">
          Clarification answers
          {time && <span className="ml-2 font-normal text-muted-foreground">{time}</span>}
        </p>
        <ul className="mt-1 space-y-1 text-sm text-muted-foreground">
          {Object.entries(input.answers).map(([q, a]) => (
            <li key={q} className="whitespace-pre-wrap">{String(a)}</li>
          ))}
        </ul>
      </div>
    );
  }
  if (input.feedback) {
    return (
      <div className="mt-2 border-l pl-3">
        <p className="text-xs font-medium">
          Asked for changes
          {time && <span className="ml-2 font-normal text-muted-foreground">{time}</span>}
        </p>
        <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">
          {input.feedback}
        </p>
      </div>
    );
  }
  // Bare actions (save/discard clicks) add no information — skip them.
  return null;
}

function LegacyTimeline({ payload }: { payload: HistoryPayload }) {
  const entries = [...(payload.history ?? [])].reverse(); // newest first

  return (
    <div className="space-y-4">
      {entries.length === 0 && !payload.genesis && (
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground">
            No history recorded for this strategy.
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
          <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">
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
          <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">
            {payload.genesis}
          </p>
        </div>
      )}
    </div>
  );
}
