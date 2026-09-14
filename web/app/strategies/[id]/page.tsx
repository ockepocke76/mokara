import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { apiFetch, getViewer, assertViewerFresh } from "@/lib/api";
import { SignInGate } from "@/components/sign-in-gate";

import { StrategyDetail } from "./strategy-detail";

export const metadata: Metadata = { title: "Strategy" };

export default async function StrategyPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ evaluate?: string }>;
}) {
  const { id } = await params;
  const { evaluate } = await searchParams;
  const viewer = await getViewer();
  assertViewerFresh(viewer);

  if (!viewer.authenticated) {
    return <SignInGate message="Sign in to view strategies." />;
  }

  const res = await apiFetch(`/strategies/${encodeURIComponent(id)}`);
  if (res.status === 404) notFound();
  if (!res.ok) {
    throw new Error(`Failed to load strategy (${res.status})`);
  }
  const strategy = await res.json();

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-10">
      <StrategyDetail
        strategy={strategy}
        autoEvaluate={evaluate === "1" && Boolean(strategy.is_owner)}
        viewerName={viewer.username || viewer.name || null}
      />
    </main>
  );
}
