"use client";

/** Leaderboard entry: medal + badge + score, expandable details with
 *  description, medal-colored radar, weighted component scores, per-scenario
 *  table, and the Clone CTA (old _display_leaderboard_entry). */
import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Data, Layout } from "plotly.js";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Markdown } from "@/components/markdown";
import { Chart } from "@/components/chart";
import type { Entry } from "./types";

const MEDALS: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };
const MEDAL_COLORS: Record<number, string> = {
  1: "#FFD700",
  2: "#C0C0C0",
  3: "#CD7F32",
};

export function categoryLabel(category: string | null): string {
  if (!category) return "—";
  return category
    .split("_")
    .map((w) => w[0] + w.slice(1).toLowerCase())
    .join(" ");
}

function hexToRgba(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

export function EntryCard({
  entry,
  category,
  profile,
  profileName,
  loggedIn,
}: {
  entry: Entry;
  category: string;
  profile: string;
  profileName: string;
  loggedIn: boolean;
}) {
  const router = useRouter();
  const [radar, setRadar] = useState<{
    data: Data[];
    layout: Partial<Layout>;
  } | null>(null);
  const [radarLoading, setRadarLoading] = useState(false);
  const [cloneState, setCloneState] = useState<
    "idle" | "busy" | "done" | "error"
  >(entry.in_library ? "done" : "idle");

  async function loadRadar() {
    if (radar || radarLoading) return;
    setRadarLoading(true);
    try {
      const res = await fetch(
        `/api/bff/leaderboard/${entry.id}/radar?category=${encodeURIComponent(category)}&profile=${encodeURIComponent(profile)}`,
      );
      if (res.ok) {
        const body = await res.json();
        const fig = body.figure as { data: Data[]; layout: Partial<Layout> };
        // Medal-colored line (old UI recolored the trace by rank)
        const color = MEDAL_COLORS[entry.rank];
        if (color && fig.data[0]) {
          const trace = fig.data[0] as Data & {
            line?: { color?: string };
            fillcolor?: string;
          };
          trace.line = { ...(trace.line ?? {}), color };
          trace.fillcolor = hexToRgba(color, 0.3);
        }
        setRadar(fig);
      }
    } finally {
      setRadarLoading(false);
    }
  }

  async function clone() {
    setCloneState("busy");
    const res = await fetch(`/api/bff/leaderboard/${entry.id}/clone`, {
      method: "POST",
    });
    if (res.ok) {
      setCloneState("done");
      router.refresh();
    } else {
      setCloneState("error");
    }
  }

  const usageBadges: string[] = [];
  if (entry.usage_clone_count > 0)
    usageBadges.push(`🔗 ${entry.usage_clone_count}`);
  if (entry.usage_fork_count > 0)
    usageBadges.push(`🔱 ${entry.usage_fork_count}`);

  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex flex-wrap items-center gap-4">
          <span className="w-12 text-center text-3xl">
            {MEDALS[entry.rank] ?? `#${entry.rank}`}
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-semibold">
              {entry.badge} {entry.strategy_name}
            </p>
            <p className="text-sm text-muted-foreground">
              Category: {categoryLabel(entry.category)}
            </p>
            {entry.is_custom && entry.author && (
              <p className="text-xs text-muted-foreground">
                👤 Created by: {entry.author}
              </p>
            )}
            {usageBadges.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {usageBadges.join(" • ")}
              </p>
            )}
          </div>
          <div className="text-right">
            <p className="text-xs text-muted-foreground">
              Excellence Score ({profileName})
            </p>
            <p className="text-3xl font-bold tabular-nums">
              {entry.score?.toFixed(1) ?? "—"}
              <span className="text-base font-normal text-muted-foreground">
                /100
              </span>
            </p>
          </div>
        </div>

        <Accordion type="single" collapsible className="mt-2">
          <AccordionItem value="details" className="border-none">
            <AccordionTrigger
              className="rounded-md border px-3 py-2 text-sm"
              onClick={() => void loadRadar()}
            >
              View Details &amp; Metrics
            </AccordionTrigger>
            <AccordionContent className="pt-3">
              {entry.description && (
                <div className="mb-4 border-b pb-4">
                  <p className="mb-1 text-sm font-semibold">
                    📝 Strategy Description
                  </p>
                  <Markdown>{entry.description}</Markdown>
                </div>
              )}

              <div className="grid gap-6 md:grid-cols-2">
                <div>
                  {radar ? (
                    <Chart
                      className="h-80"
                      data={radar.data}
                      layout={{
                        ...radar.layout,
                        autosize: true,
                        width: undefined,
                      }}
                    />
                  ) : (
                    <Skeleton className="h-80 w-full" />
                  )}
                </div>
                <div>
                  <p className="mb-2 text-sm font-semibold">
                    🎯 Component Scores
                  </p>
                  <div className="grid grid-cols-2 gap-3">
                    {entry.metric_grid.map((m) => (
                      <div key={m.key} className="leading-tight">
                        <p className="text-xs text-muted-foreground">
                          {m.name}
                        </p>
                        <p className="text-lg font-bold tabular-nums">
                          {m.score.toFixed(0)}
                        </p>
                        <p className="text-[11px] text-muted-foreground">
                          {m.weight > 0
                            ? `${(m.weight * 100).toFixed(0)}% Weight (${profileName})`
                            : "Informational"}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {entry.scenario_results.length > 0 && (
                <div className="mt-4 border-t pt-4">
                  <p className="mb-2 text-sm font-semibold">
                    Performance by Scenario:
                  </p>
                  <div className="overflow-hidden rounded-lg border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Scenario</TableHead>
                          <TableHead className="text-right">
                            Sortino Ratio
                          </TableHead>
                          <TableHead className="text-right">
                            Success Rate
                          </TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {entry.scenario_results.map((s) => (
                          <TableRow key={s.name}>
                            <TableCell className="text-sm">{s.name}</TableCell>
                            <TableCell className="text-right text-sm tabular-nums">
                              {s.sortino_ratio?.toFixed(2) ?? "—"}
                            </TableCell>
                            <TableCell className="text-right text-sm tabular-nums">
                              {s.success_rate !== null
                                ? `${(s.success_rate * 100).toFixed(1)}%`
                                : "—"}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              )}

              <div className="mt-4 border-t pt-4">
                <p className="text-sm font-semibold">📋 Clone This Strategy</p>
                <p className="mb-2 text-xs text-muted-foreground">
                  Start with this proven strategy and customize it to your
                  needs
                </p>
                {!loggedIn ? (
                  <p className="text-xs text-muted-foreground">
                    Log in to clone
                  </p>
                ) : !entry.clone_target_id ? (
                  <p className="text-xs text-muted-foreground">
                    ⚠️ Clone not available for this strategy
                  </p>
                ) : cloneState === "done" ? (
                  <Button variant="outline" size="sm" disabled>
                    ✅ In Library
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => void clone()}
                    disabled={cloneState === "busy"}
                  >
                    {cloneState === "busy"
                      ? "Cloning…"
                      : cloneState === "error"
                        ? "Clone failed — retry"
                        : `📋 Clone ${entry.strategy_name}`}
                  </Button>
                )}
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  );
}
