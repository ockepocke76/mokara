import type { Metadata } from "next";
import Link from "next/link";

import { apiFetch, getViewer } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata: Metadata = { title: "Strategies" };

type StrategyRow = {
  id: number;
  user_id: number;
  strategy_name: string;
  description?: string | null;
  ai_description?: string | null;
  validation_status?: string | null;
  is_public?: boolean;
  excellence_score?: number | null;
  has_evaluation?: boolean;
  updated_at?: string;
};

type ActiveRun = {
  id: string;
  status: string;
  strategy_name?: string | null;
  user_request: string;
};

export default async function StrategiesPage() {
  const viewer = await getViewer();

  if (!viewer.authenticated) {
    return (
      <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-24 text-center">
        <h1 className="text-3xl font-semibold tracking-tight">Strategies</h1>
        <p className="text-muted-foreground">
          Sign in to design and manage strategies.
        </p>
        <Button asChild>
          <Link href="/login">Sign in</Link>
        </Button>
      </main>
    );
  }

  const res = await apiFetch("/strategies");
  if (!res.ok) {
    throw new Error(`Failed to load strategies (${res.status})`);
  }
  const body = await res.json();
  const strategies: StrategyRow[] = body.strategies ?? [];
  const activeRuns: ActiveRun[] = body.active_runs ?? [];
  const mine = strategies.filter((s) => s.user_id === viewer.id);
  const community = strategies.filter((s) => s.user_id !== viewer.id);

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-10">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Strategies</h1>
          <p className="text-sm text-muted-foreground">
            {mine.length} of yours · {community.length} shared by the community
          </p>
        </div>
        <Button asChild>
          <Link href="/strategies/new">Design a strategy</Link>
        </Button>
      </div>

      {activeRuns.map((run) => (
        <Link key={run.id} href={`/strategies/new?run=${run.id}`}>
          <Card className="mb-4 border-amber-500/50 transition-colors hover:bg-muted/50">
            <CardContent className="flex items-center justify-between py-4 text-sm">
              <span>
                {run.status === "needs_input" ? (
                  <>
                    <span className="font-medium">
                      {run.strategy_name || "Your strategy"}
                    </span>{" "}
                    has a question for you
                  </>
                ) : (
                  <>
                    Still working on{" "}
                    <span className="font-medium">
                      {run.strategy_name || "your strategy"}
                    </span>
                    …
                  </>
                )}
              </span>
              <Badge variant="outline">
                {run.status === "needs_input" ? "needs you" : "running"}
              </Badge>
            </CardContent>
          </Card>
        </Link>
      ))}

      {mine.length === 0 && activeRuns.length === 0 ? (
        <p className="py-16 text-center text-muted-foreground">
          No strategies yet —{" "}
          <Link href="/strategies/new" className="underline">
            design your first
          </Link>
          .
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          {mine.map((s) => (
            <StrategyCard key={s.id} strategy={s} />
          ))}
        </div>
      )}

      {community.length > 0 && (
        <>
          <h2 className="mb-4 mt-10 text-xl font-semibold tracking-tight">
            Community strategies
          </h2>
          <div className="flex flex-col gap-4">
            {community.map((s) => (
              <StrategyCard key={s.id} strategy={s} />
            ))}
          </div>
        </>
      )}
    </main>
  );
}

function StrategyCard({ strategy }: { strategy: StrategyRow }) {
  const description = strategy.ai_description || strategy.description || "";
  return (
    <Link href={`/strategies/${strategy.id}`}>
      <Card className="transition-colors hover:bg-muted/50">
        <CardHeader className="pb-2">
          <CardTitle className="flex flex-wrap items-center gap-2 text-base">
            {strategy.strategy_name}
            {strategy.validation_status === "validated" && (
              <Badge variant="secondary">validated</Badge>
            )}
            {strategy.validation_status === "failed" && (
              <Badge variant="destructive">draft — failed checks</Badge>
            )}
            {strategy.is_public && <Badge variant="outline">public</Badge>}
            {strategy.has_evaluation &&
              typeof strategy.excellence_score === "number" && (
                <Badge variant="outline">
                  score {strategy.excellence_score.toFixed(1)}
                </Badge>
              )}
          </CardTitle>
        </CardHeader>
        {description && (
          <CardContent className="pt-0 text-sm text-muted-foreground">
            <p className="line-clamp-2">{description}</p>
          </CardContent>
        )}
      </Card>
    </Link>
  );
}
