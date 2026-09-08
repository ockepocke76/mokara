import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { apiFetch, getViewer } from "@/lib/api";
import { Button } from "@/components/ui/button";

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

  if (!viewer.authenticated) {
    return (
      <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-24 text-center">
        <p className="text-muted-foreground">Sign in to view strategies.</p>
        <Button asChild>
          <Link href="/login">Sign in</Link>
        </Button>
      </main>
    );
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
      />
    </main>
  );
}
