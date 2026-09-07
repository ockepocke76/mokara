import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { apiFetch } from "@/lib/api";
import { ReportView, type ReportItem } from "./report-view";
import { PdfButton } from "./pdf-button";

export const metadata: Metadata = { title: "Simulation results" };

export default async function SimulationResultsPage({
  params,
}: {
  params: Promise<{ hash: string }>;
}) {
  const { hash } = await params;

  const [reportRes, resultsRes] = await Promise.all([
    apiFetch(`/simulations/${encodeURIComponent(hash)}/report`),
    apiFetch(`/simulations/${encodeURIComponent(hash)}/results`),
  ]);
  if (reportRes.status === 404) notFound();
  if (!reportRes.ok) throw new Error(`report fetch failed: ${reportRes.status}`);
  const report: { items: ReportItem[] } = await reportRes.json();
  const meta = resultsRes.ok
    ? ((await resultsRes.json()) as {
        params: Record<string, string | number | null>;
      })
    : null;

  const p = meta?.params;

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            📊 {p?.simulation_name || "Simulation results"}
          </h1>
          {p && (
            <p className="text-sm text-muted-foreground">
              {String(p.custom_strategy_name ?? p.strategy)} ·{" "}
              {String(p.asset_name ?? p.asset_model)} · {String(p.num_years)}{" "}
              years · {Number(p.num_simulations).toLocaleString()} runs
            </p>
          )}
        </div>
        <PdfButton hash={hash} />
      </div>
      <ReportView items={report.items} />
    </main>
  );
}
