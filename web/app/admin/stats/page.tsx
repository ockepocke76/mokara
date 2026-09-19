import type { Metadata } from "next";

import { apiFetch } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata: Metadata = { title: "Admin · Statistics" };

type TierCount = { tier: string; count: number };
type UserCount = { email: string; count: number };
type Stats = {
  total_users: number;
  total_simulations: number;
  total_strategies: number;
  tier_distribution: TierCount[];
  top_by_simulations: UserCount[];
  top_by_strategies: UserCount[];
};

function Bar({ label, count, max }: { label: string; count: number; max: number }) {
  const pct = max > 0 ? Math.max((count / max) * 100, 2) : 0;
  return (
    <div className="flex items-center gap-2 text-sm">
      <div className="w-40 shrink-0 truncate text-muted-foreground">
        {label}
      </div>
      <div className="h-3 flex-1 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      <div className="w-10 shrink-0 text-right tabular-nums">{count}</div>
    </div>
  );
}

export default async function AdminStatsPage() {
  const res = await apiFetch("/admin/stats");
  const stats: Stats = await res.json();

  const tierMax = Math.max(1, ...stats.tier_distribution.map((t) => t.count));
  const simMax = Math.max(1, ...stats.top_by_simulations.map((u) => u.count));
  const stratMax = Math.max(1, ...stats.top_by_strategies.map((u) => u.count));

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>Total Users</CardDescription>
            <CardTitle className="text-2xl">{stats.total_users}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Total Simulations</CardDescription>
            <CardTitle className="text-2xl">
              {stats.total_simulations.toLocaleString()}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Total Strategies</CardDescription>
            <CardTitle className="text-2xl">
              {stats.total_strategies.toLocaleString()}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Users by Tier</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {stats.tier_distribution.map((t) => (
            <Bar key={t.tier} label={t.tier} count={t.count} max={tierMax} />
          ))}
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Top Users — Simulations</CardTitle>
            <CardDescription>Top 20 by simulation count</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {stats.top_by_simulations.length === 0 ? (
              <span className="text-sm text-muted-foreground">No data yet.</span>
            ) : (
              stats.top_by_simulations.map((u) => (
                <Bar key={u.email} label={u.email} count={u.count} max={simMax} />
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top Users — Strategies</CardTitle>
            <CardDescription>Top 20 by strategy count</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {stats.top_by_strategies.length === 0 ? (
              <span className="text-sm text-muted-foreground">No data yet.</span>
            ) : (
              stats.top_by_strategies.map((u) => (
                <Bar key={u.email} label={u.email} count={u.count} max={stratMax} />
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
