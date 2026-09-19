"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";

export type DemoSimulation = {
  id: number;
  simulation_hash: string;
  simulation_name: string;
  email: string;
  timestamp: string;
  is_public: boolean;
};

export type DemoStrategy = {
  id: number;
  strategy_name: string;
  email: string;
  created_at: string;
  is_public: boolean;
};

export function DemoContentLists({
  simulations,
  strategies,
}: {
  simulations: DemoSimulation[];
  strategies: DemoStrategy[];
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);

  async function toggleSimulation(hash: string, isPublic: boolean) {
    setBusy(`sim-${hash}`);
    await fetch(`/api/bff/admin/simulations/${encodeURIComponent(hash)}/public`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_public: isPublic }),
    });
    setBusy(null);
    router.refresh();
  }

  async function toggleStrategy(id: number, isPublic: boolean) {
    setBusy(`strat-${id}`);
    await fetch(`/api/bff/admin/strategies/${id}/public`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_public: isPublic }),
    });
    setBusy(null);
    router.refresh();
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Demo Simulations</CardTitle>
          <CardDescription>
            {simulations.length === 0
              ? "No admin-owned simulations yet."
              : `${simulations.length} shown`}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {simulations.map((s) => (
            <div
              key={s.id}
              className="flex items-center justify-between gap-2 rounded-lg border border-border px-2.5 py-1.5"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium">
                    {s.simulation_name}
                  </span>
                  {s.is_public && (
                    <Badge variant="outline" className="shrink-0">
                      public
                    </Badge>
                  )}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {s.email} ·{" "}
                  <time dateTime={s.timestamp} suppressHydrationWarning>
                    {new Date(s.timestamp).toLocaleDateString()}
                  </time>
                </div>
              </div>
              <Checkbox
                checked={s.is_public}
                disabled={busy === `sim-${s.simulation_hash}`}
                onCheckedChange={(checked) =>
                  toggleSimulation(s.simulation_hash, checked === true)
                }
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Public Strategies</CardTitle>
          <CardDescription>
            {strategies.length === 0
              ? "No admin-owned strategies yet."
              : `${strategies.length} shown`}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {strategies.map((s) => (
            <div
              key={s.id}
              className="flex items-center justify-between gap-2 rounded-lg border border-border px-2.5 py-1.5"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium">
                    {s.strategy_name}
                  </span>
                  {s.is_public && (
                    <Badge variant="outline" className="shrink-0">
                      public
                    </Badge>
                  )}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {s.email} ·{" "}
                  <time dateTime={s.created_at} suppressHydrationWarning>
                    {new Date(s.created_at).toLocaleDateString()}
                  </time>
                </div>
              </div>
              <Checkbox
                checked={s.is_public}
                disabled={busy === `strat-${s.id}`}
                onCheckedChange={(checked) =>
                  toggleStrategy(s.id, checked === true)
                }
              />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
