import type { Metadata } from "next";
import Link from "next/link";

import { apiFetch, getViewer } from "@/lib/api";
import { Button } from "@/components/ui/button";

import { Designer } from "./designer";

export const metadata: Metadata = { title: "Strategy Designer" };

export default async function NewStrategyPage({
  searchParams,
}: {
  searchParams: Promise<{ seed?: string; run?: string }>;
}) {
  const { seed, run } = await searchParams;
  const viewer = await getViewer();

  if (!viewer.authenticated) {
    return (
      <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-24 text-center">
        <h1 className="text-3xl font-semibold tracking-tight">Strategy Designer</h1>
        <p className="text-muted-foreground">Sign in to design strategies.</p>
        <Button asChild>
          <Link href="/login">Sign in</Link>
        </Button>
      </main>
    );
  }

  let seedStrategy: { id: number; strategy_name: string } | null = null;
  if (seed) {
    const res = await apiFetch(`/strategies/${encodeURIComponent(seed)}`);
    if (res.ok) {
      const body = await res.json();
      seedStrategy = { id: body.id, strategy_name: body.strategy_name };
    }
  }

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
      <div className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">
          {seedStrategy ? "Evolve strategy" : "Design a strategy"}
        </h1>
        <p className="text-sm text-muted-foreground">
          An AI workflow builds it step by step — you review before anything is
          saved.
        </p>
      </div>
      <Designer seedStrategy={seedStrategy} initialRunId={run ?? null} />
    </main>
  );
}
