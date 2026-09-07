import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { apiFetch, getViewer } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { HistoryItem } from "@/app/simulations/simulation-card";

export const metadata: Metadata = { title: "Home" };

export default async function DashboardPage() {
  const viewer = await getViewer();

  if (!viewer.authenticated) {
    const spotsLeft = Math.max(
      0,
      viewer.beta.max_users - viewer.beta.current_users,
    );
    return (
      <main className="flex flex-1 flex-col items-center justify-center gap-6 px-6 py-24 text-center">
        <Image
          src="/mokara-mark.jpg"
          alt="Mokara"
          width={96}
          height={96}
          priority
        />
        <h1 className="text-5xl font-bold tracking-tight">mokara.ai</h1>
        <p className="text-lg text-muted-foreground">
          Wisdom of the Crowd, Applied
        </p>
        <p className="max-w-md text-muted-foreground">
          Design, stress-test and share investment strategies across thousands
          of Monte Carlo futures.
        </p>
        <div className="flex items-center gap-3">
          <Button asChild size="lg">
            <Link href="/login">
              {viewer.beta.is_full
                ? "Sign in"
                : `Join early access — ${spotsLeft} spots left`}
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/leaderboard">🏆 View Leaderboard</Link>
          </Button>
        </div>
      </main>
    );
  }

  const [statsRes, simsRes] = await Promise.all([
    apiFetch("/me/stats"),
    apiFetch("/simulations"),
  ]);
  const stats = statsRes.ok
    ? await statsRes.json()
    : { simulations: 0, strategies: 0 };
  const sims: { items: HistoryItem[] } = simsRes.ok
    ? await simsRes.json()
    : { items: [] };
  const recent = sims.items.slice(0, 5);

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-10">
      <h1 className="mb-6 text-3xl font-bold tracking-tight">
        Welcome back, {viewer.name ?? "there"} 👋
      </h1>

      <div className="mb-8 grid grid-cols-2 gap-6 sm:max-w-md">
        <div>
          <p className="text-sm text-muted-foreground">Simulations Run</p>
          <p className="text-4xl font-bold tabular-nums">{stats.simulations}</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Strategies Created</p>
          <p className="text-4xl font-bold tabular-nums">{stats.strategies}</p>
        </div>
      </div>

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold">Recent simulations</h2>
        {recent.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Here are your recent simulations — none yet.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {recent.map((s) => (
              <Card key={s.history_id}>
                <CardContent className="flex items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <Link
                      href={`/simulations/${s.simulation_hash}`}
                      className="font-medium hover:underline"
                    >
                      {s.name || "Untitled simulation"}
                    </Link>
                    <p className="truncate text-xs text-muted-foreground">
                      {s.description}
                    </p>
                  </div>
                  {typeof s.success_rate === "number" && (
                    <span className="shrink-0 text-sm font-semibold tabular-nums">
                      {(s.success_rate * 100).toFixed(0)}%
                    </span>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Quick Actions</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <Button asChild size="lg">
            <Link href="/simulate">🚀 Run New Simulation</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/strategies">✨ Design Strategy</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/leaderboard">🏆 View Leaderboard</Link>
          </Button>
        </div>
      </section>
    </main>
  );
}
