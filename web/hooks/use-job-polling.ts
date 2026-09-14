"use client";

import { useEffect, useState } from "react";

/** Same cadence as the previous inline loop in simulate-form. */
const POLL_MS = 1_500;
/** Failed polls back off to this spacing so a redeploy isn't hammered. */
const FAILURE_RETRY_MS = 4_000;
/** Consecutive failed polls (network error or non-OK) before giving up.
 *  15 × 4s ≈ 60s of tolerance — enough to ride out a rolling redeploy or
 *  worker restart (review: 12s was shorter than a realistic outage). */
const MAX_CONSECUTIVE_FAILURES = 15;

export type Job = {
  status: string;
  error?: string | null;
  progress_message?: string | null;
  progress_value?: number | null;
};

/**
 * Polls `/api/bff/jobs/{jobId}` on a setTimeout cadence while `jobId` is
 * non-null, exposing the latest job snapshot. Stops on terminal states
 * (COMPLETED / FAILED), after MAX_CONSECUTIVE_FAILURES failed polls in a row
 * (surfaced via `error`), and on unmount or jobId change (timer cleared,
 * in-flight fetch aborted). A successful poll resets the failure counter.
 */
export function useJobPolling(jobId: string | null) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reset stale results as soon as the target job changes (render-time
  // adjustment, per React's "adjusting state when a prop changes" pattern) —
  // a leftover COMPLETED snapshot from a previous job must never leak into
  // a new poll cycle.
  const [lastJobId, setLastJobId] = useState(jobId);
  if (jobId !== lastJobId) {
    setLastJobId(jobId);
    setJob(null);
    setError(null);
  }

  useEffect(() => {
    if (!jobId) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const controller = new AbortController();
    let failures = 0;

    const failOnce = () => {
      failures += 1;
      if (failures >= MAX_CONSECUTIVE_FAILURES) {
        setError("Lost contact with the simulation job — please try again.");
      } else {
        timer = setTimeout(() => void poll(), FAILURE_RETRY_MS);
      }
    };

    const poll = async () => {
      try {
        const res = await fetch(`/api/bff/jobs/${jobId}`, {
          signal: controller.signal,
        });
        if (cancelled) return;
        if (!res.ok) {
          failOnce();
          return;
        }
        const body = (await res.json()) as Job;
        if (cancelled) return;
        failures = 0;
        setJob(body);
        if (body.status !== "COMPLETED" && body.status !== "FAILED") {
          timer = setTimeout(() => void poll(), POLL_MS);
        }
      } catch {
        if (!cancelled) failOnce();
      }
    };

    timer = setTimeout(() => void poll(), POLL_MS);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      controller.abort();
    };
  }, [jobId]);

  return { job, error };
}
