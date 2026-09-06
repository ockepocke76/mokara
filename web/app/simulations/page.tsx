import type { Metadata } from "next";
import Link from "next/link";

import { apiFetch, getViewer } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { SimulationCard, type HistoryItem } from "./simulation-card";

export const metadata: Metadata = { title: "My Simulations" };

export default async function SimulationsPage() {
  const viewer = await getViewer();

  if (!viewer.authenticated) {
    return (
      <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-24 text-center">
        <h1 className="text-3xl font-semibold tracking-tight">
          My Simulations
        </h1>
        <p className="text-muted-foreground">
          Sign in to see your simulation history.
        </p>
        <Button asChild>
          <Link href="/login">Sign in</Link>
        </Button>
      </main>
    );
  }

  const res = await apiFetch("/simulations");
  const { items }: { items: HistoryItem[] } = await res.json();

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-10">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            My Simulations
          </h1>
          <p className="text-sm text-muted-foreground">
            {items.length} saved simulation{items.length === 1 ? "" : "s"}
          </p>
        </div>
        <Button asChild>
          <Link href="/simulate">New simulation</Link>
        </Button>
      </div>

      {items.length === 0 ? (
        <p className="py-16 text-center text-muted-foreground">
          No simulations yet —{" "}
          <Link href="/simulate" className="underline">
            run your first
          </Link>
          .
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          {items.map((item) => (
            <SimulationCard key={item.history_id} item={item} />
          ))}
        </div>
      )}
    </main>
  );
}
