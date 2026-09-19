"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";

export type EvaluationStrategies = {
  builtins: string[];
  customs: { id: number; user_id: number; strategy_name: string }[];
};

type EvalStatus = {
  total: number;
  completed: number;
  failed: number;
  processing: number;
  pending: number;
  progress: number;
  running: boolean;
  current_strategy: string | null;
};

const JOBS_KEY = "admin-eval-jobs";

// Job ids of the latest run live in localStorage so a reload keeps tracking
// it (or shows its final summary); exposed as an external store so the
// server snapshot (no jobs) and the first client render agree.
const listeners = new Set<() => void>();

function readJobs(): string {
  try {
    return localStorage.getItem(JOBS_KEY) ?? "[]";
  } catch {
    return "[]";
  }
}

function subscribeJobs(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

function saveJobs(ids: string[]) {
  try {
    if (ids.length) localStorage.setItem(JOBS_KEY, JSON.stringify(ids));
    else localStorage.removeItem(JOBS_KEY);
  } catch {}
  listeners.forEach((cb) => cb());
}

export function EvaluationsPanel({ strategies }: { strategies: EvaluationStrategies }) {
  const [builtins, setBuiltins] = useState<Set<string>>(new Set(strategies.builtins));
  const [customs, setCustoms] = useState<Set<number>>(new Set());
  const jobsRaw = useSyncExternalStore(subscribeJobs, readJobs, () => "[]");
  const jobIds = useMemo<string[]>(() => JSON.parse(jobsRaw), [jobsRaw]);
  const [status, setStatus] = useState<EvalStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const running = jobIds.length > 0 && (status?.running ?? true);

  const [pollError, setPollError] = useState<string | null>(null);

  useEffect(() => {
    if (!running) return;
    let cancelled = false;
    let failures = 0;
    const timer = setInterval(() => void poll(), 1000);
    async function poll() {
      try {
        const res = await fetch(
          `/api/bff/admin/evaluations/status?job_ids=${encodeURIComponent(jobIds.join(","))}`,
        );
        if (!res.ok) throw new Error(`status check failed (${res.status})`);
        const body: EvalStatus = await res.json();
        if (cancelled) return;
        failures = 0;
        setPollError(null);
        setStatus(body);
      } catch (err) {
        if (cancelled) return;
        failures += 1;
        setPollError(err instanceof Error ? err.message : "status check failed");
        if (failures >= 10) {
          // Stop hammering a dead API; the jobs stay tracked in localStorage,
          // so a reload resumes once it's back.
          clearInterval(timer);
          setPollError("Lost contact with the API — reload to resume tracking.");
        }
      }
    }
    void poll();
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [running, jobIds]);

  const selectedCount = builtins.size + customs.size;

  async function start() {
    setStarting(true);
    setError(null);
    setStatus(null);
    const res = await fetch("/api/bff/admin/evaluations/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        builtin_names: [...builtins],
        custom_strategy_ids: [...customs],
      }),
    });
    setStarting(false);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(body.detail ?? "Failed to queue evaluations.");
      return;
    }
    const body: { job_ids: string[] } = await res.json();
    saveJobs(body.job_ids);
  }

  function toggle<T>(set: Set<T>, value: T, on: boolean): Set<T> {
    const next = new Set(set);
    if (on) next.add(value);
    else next.delete(value);
    return next;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Leaderboard evaluations</CardTitle>
        <CardDescription>
          Each strategy runs across 8 market scenarios (200 simulations each)
          as a background job. All evaluations use ISK taxation; rankings
          don&apos;t account for exit taxation.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <fieldset disabled={running} className="flex flex-col gap-1.5">
            <legend className="mb-1 text-sm font-medium">Built-in strategies</legend>
            {strategies.builtins.map((name) => (
              <label key={name} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={builtins.has(name)}
                  onCheckedChange={(c) => setBuiltins(toggle(builtins, name, c === true))}
                />
                {name}
              </label>
            ))}
          </fieldset>
          <fieldset disabled={running} className="flex flex-col gap-1.5">
            <legend className="mb-1 text-sm font-medium">
              Custom strategies ({strategies.customs.length})
            </legend>
            {strategies.customs.length === 0 && (
              <span className="text-sm text-muted-foreground">
                No custom strategies saved by any users yet.
              </span>
            )}
            <div className="flex max-h-56 flex-col gap-1.5 overflow-y-auto">
              {strategies.customs.map((cs) => (
                <label key={cs.id} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={customs.has(cs.id)}
                    onCheckedChange={(c) => setCustoms(toggle(customs, cs.id, c === true))}
                  />
                  <span className="truncate">
                    {cs.strategy_name}
                    <span className="text-muted-foreground"> · user {cs.user_id}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={start} disabled={running || starting || selectedCount === 0}>
            {starting ? "Queuing…" : `Start evaluation (${selectedCount})`}
          </Button>
          <span className="text-sm text-muted-foreground">
            one job per strategy · worker must be running
          </span>
          {(error ?? pollError) && (
            <span className="text-sm text-destructive">{error ?? pollError}</span>
          )}
        </div>

        {jobIds.length > 0 && status && (
          <div className="flex flex-col gap-1.5">
            <Progress value={status.progress * 100} />
            <p className="text-sm text-muted-foreground">
              {status.running
                ? `${status.current_strategy ? `${status.current_strategy}… ` : "Waiting for worker… "}(${status.completed + status.failed}/${status.total})`
                : `Done: ${status.completed} completed${status.failed ? `, ${status.failed} failed` : ""}.`}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
