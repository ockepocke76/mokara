import type { Metadata } from "next";
import Link from "next/link";

import { apiFetch, getViewer } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Chart } from "@/components/chart";

export const metadata: Metadata = { title: "Dashboard" };

type CommunityStats = {
  total_simulations: number;
  total_strategies: number;
  total_years_simulated: number;
  top_strategies: { strategy_identifier: string; count: number }[];
};

export default async function DashboardPage() {
  const [viewer, statsRes] = await Promise.all([
    getViewer(),
    apiFetch("/community-stats"),
  ]);
  const stats: CommunityStats = await statsRes.json();

  const top = (stats.top_strategies ?? []).slice().reverse();

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
      <h1 className="mb-1 text-3xl font-semibold tracking-tight">Dashboard</h1>
      <p className="mb-8 text-sm text-muted-foreground">
        {viewer.authenticated
          ? `Welcome back${viewer.name ? `, ${viewer.name}` : ""}.`
          : "Community overview — sign in to run your own simulations."}
      </p>

      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Simulations run"
          value={stats.total_simulations.toLocaleString()}
        />
        <StatCard
          label="Strategies created"
          value={stats.total_strategies.toLocaleString()}
        />
        <StatCard
          label="Years simulated"
          value={stats.total_years_simulated.toLocaleString()}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Most-run strategies</CardTitle>
            <CardDescription>Completed simulation runs</CardDescription>
          </CardHeader>
          <CardContent>
            {top.length === 0 ? (
              <p className="py-12 text-center text-sm text-muted-foreground">
                No completed simulations yet — be the first:{" "}
                <Link href="/simulate" className="underline">
                  run a simulation
                </Link>
                .
              </p>
            ) : (
              <Chart
                className="h-72"
                data={[
                  {
                    type: "bar",
                    orientation: "h",
                    x: top.map((s) => s.count),
                    y: top.map((s) => s.strategy_identifier),
                    marker: { color: "#171717" },
                  },
                ]}
                layout={{
                  xaxis: { title: { text: "runs" } },
                  yaxis: { automargin: true },
                }}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Getting started</CardTitle>
            <CardDescription>What you can do on Mokara</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            <Link href="/simulate" className="underline">
              Run a Monte Carlo simulation
            </Link>
            <Link href="/leaderboard" className="underline">
              Browse the strategy leaderboard
            </Link>
            <Link href="/strategies" className="underline">
              Design a strategy with AI
            </Link>
            <Link href="/docs/methodology" className="underline">
              Read the methodology
            </Link>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-3xl tabular-nums">{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}
