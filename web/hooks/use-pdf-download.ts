"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Cadence and bound match the previous inline loops: 120 × 2 s ≈ 4 min. */
const POLL_MS = 2_000;
const MAX_POLLS = 120;

export type PdfDownloadStatus = "idle" | "working" | "error";

/**
 * Queue → poll → download flow for a simulation's PDF report, shared by the
 * detail page's PdfButton and the history list's SimulationCard.
 *
 * `start()` POSTs `/api/bff/simulations/{hash}/pdf`, polls `…/pdf/status`
 * until ready/failed (bounded), then triggers the browser download via an
 * anchor click. Teardown-safe: unmount aborts in-flight fetches and no state
 * is set afterwards.
 */
export function usePdfDownload(hash: string) {
  const [status, setStatus] = useState<PdfDownloadStatus>("idle");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const start = useCallback(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const { signal } = controller;

    const run = async () => {
      setStatus("working");
      const res = await fetch(`/api/bff/simulations/${hash}/pdf`, {
        method: "POST",
        signal,
      });
      if (signal.aborted) return;
      if (!res.ok) {
        setStatus("error");
        return;
      }
      for (let i = 0; i < MAX_POLLS; i++) {
        await new Promise((r) => setTimeout(r, POLL_MS));
        if (signal.aborted) return;
        const s = await fetch(`/api/bff/simulations/${hash}/pdf/status`, {
          signal,
        });
        if (!s.ok) continue;
        const body = await s.json();
        if (signal.aborted) return;
        if (body.pdf_status === "ready") {
          const a = document.createElement("a");
          a.href = `/api/bff/simulations/${hash}/pdf`;
          a.download = "";
          a.click();
          setStatus("idle");
          return;
        }
        if (body.pdf_status === "failed") {
          setStatus("error");
          return;
        }
      }
      setStatus("error");
    };

    run().catch(() => {
      if (!signal.aborted) setStatus("error");
    });
  }, [hash]);

  return { status, start };
}
