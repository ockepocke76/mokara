import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { apiFetch } from "@/lib/api";
import { ResultsView, type SimulationResults } from "./results-view";

export const metadata: Metadata = { title: "Simulation results" };

export default async function SimulationResultsPage({
  params,
}: {
  params: Promise<{ hash: string }>;
}) {
  const { hash } = await params;
  const res = await apiFetch(
    `/simulations/${encodeURIComponent(hash)}/results`,
  );
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`results fetch failed: ${res.status}`);
  const results: SimulationResults = await res.json();

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
      <ResultsView results={results} />
    </main>
  );
}
