"use client";

/** Evaluation tab: radar + component scores + per-scenario table for the
 *  strategy's full evaluation (old Info tab's right column). Three states:
 *  not evaluated (CTA), in progress (auto-refresh), done. */
import { useEffect, useRef, useState } from "react";
import type { Data, Layout } from "plotly.js";
import { toast } from "sonner";

import { categoryLabel } from "@/lib/strategy-format";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  EvaluationRadarScores,
  ScenarioTable,
  type MetricCell,
  type ScenarioRow,
} from "@/components/evaluation-results";
type EvaluationPayload = {
  evaluation: Record<string, unknown> | null;
  in_progress: boolean;
  radar?: { data: Data[]; layout: Partial<Layout> } | null;
  metric_grid?: MetricCell[];
};

const POLL_MS = 10_000;

export function EvaluationTab({
  strategyId,
  isOwner,
  hasCode,
  autoStart = false,
}: {
  strategyId: number;
  isOwner: boolean;
  hasCode: boolean;
  /** The designer's "Save & evaluate" CTA (?evaluate=1): queue on mount. */
  autoStart?: boolean;
}) {
  const [payload, setPayload] = useState<EvaluationPayload | null>(null);
  const [queueing, setQueueing] = useState(false);
  // Bumping `tick` refetches; while a job is in progress (or nothing has
  // loaded yet) the effect schedules its own next bump, giving a poll loop
  // with clean teardown that also survives individual failed polls.
  const [tick, setTick] = useState(0);
  const payloadRef = useRef<EvaluationPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const scheduleNext = () => {
      if (!cancelled && (!payloadRef.current || payloadRef.current.in_progress)) {
        timer = setTimeout(() => setTick((t) => t + 1), POLL_MS);
      }
    };
    (async () => {
      try {
        const res = await fetch(`/api/bff/strategies/${strategyId}/evaluation`);
        if (cancelled) return;
        if (!res.ok) {
          scheduleNext();
          return;
        }
        const body = (await res.json()) as EvaluationPayload;
        if (cancelled) return;
        payloadRef.current = body;
        setPayload(body);
        scheduleNext();
      } catch {
        scheduleNext();
      }
    })();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [strategyId, tick]);

  async function queueEvaluation() {
    setQueueing(true);
    try {
      const res = await fetch(`/api/bff/strategies/${strategyId}/evaluate`, {
        method: "POST",
      });
      if (res.ok) {
        toast.success("Full evaluation queued — results appear here when done.");
        const next: EvaluationPayload = {
          ...(payloadRef.current ?? { evaluation: null }),
          in_progress: true,
        };
        payloadRef.current = next;
        setPayload(next);
        setTick((t) => t + 1);
      } else {
        toast.error("Could not queue the evaluation.");
      }
    } catch {
      toast.error("Could not queue the evaluation.");
    } finally {
      setQueueing(false);
    }
  }

  const autoStarted = useRef(false);
  useEffect(() => {
    if (!autoStart || autoStarted.current) return;
    autoStarted.current = true;
    void queueEvaluation().finally(() => {
      // Strip the query even on failure — a reload must not double-queue.
      window.history.replaceState(null, "", `/strategies/${strategyId}`);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStart]);

  if (!payload) {
    return <Skeleton className="h-64 w-full" />;
  }

  const { evaluation, in_progress, radar, metric_grid } = payload;

  if (in_progress && !evaluation) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          ⏳ Evaluation in progress — 1,000+ simulation paths across scenarios.
          This page refreshes itself; results usually land within a few minutes.
        </CardContent>
      </Card>
    );
  }

  if (!evaluation) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-8 text-center">
          <p className="text-sm text-muted-foreground">
            Not evaluated yet. A full evaluation runs 1,000+ simulation paths
            across stress scenarios and scores the strategy for the
            leaderboard.
          </p>
          {isOwner && hasCode ? (
            <Button onClick={() => void queueEvaluation()} disabled={queueing}>
              {queueing ? "Queueing…" : "Run full evaluation"}
            </Button>
          ) : (
            <p className="text-xs text-muted-foreground">
              Only the owner can trigger an evaluation.
            </p>
          )}
        </CardContent>
      </Card>
    );
  }

  const score = evaluation.excellence_score as number | null | undefined;
  const scenarios = (evaluation.scenario_results ?? []) as ScenarioRow[];
  const evaluatedAt =
    typeof evaluation.created_at === "string"
      ? evaluation.created_at.slice(0, 16).replace("T", " ")
      : null;

  return (
    <div className="space-y-6">
      {in_progress && (
        <p className="text-sm text-muted-foreground">
          ⏳ A re-evaluation is running — the scores below are the previous
          result and refresh automatically.
        </p>
      )}

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs text-muted-foreground">Excellence Score</p>
          <p className="text-4xl font-bold tabular-nums">
            {typeof score === "number" ? score.toFixed(1) : "—"}
            <span className="text-base font-normal text-muted-foreground">
              /100
            </span>
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Category: {categoryLabel((evaluation.strategy_category as string | null) ?? null)}
            {evaluatedAt && ` · evaluated ${evaluatedAt}`}
          </p>
        </div>
        {isOwner && hasCode && !in_progress && (
          <Button
            variant="outline"
            onClick={() => void queueEvaluation()}
            disabled={queueing}
          >
            {queueing ? "Queueing…" : "Re-run evaluation"}
          </Button>
        )}
      </div>

      <EvaluationRadarScores radar={radar} metricGrid={metric_grid ?? []} />

      <ScenarioTable scenarios={scenarios} />
    </div>
  );
}
