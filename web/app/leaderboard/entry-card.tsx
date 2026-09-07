"use client";

import { useState } from "react";
import type { Data, Layout } from "plotly.js";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Chart } from "@/components/chart";

export type Entry = {
  rank: number;
  id: number;
  strategy_name: string;
  category: string | null;
  is_custom: boolean;
  author: string | null;
  score: number | null;
  scores: Record<string, number | null>;
};

const MEDALS = ["🥇", "🥈", "🥉"];

const SCORE_LABELS: Record<string, string> = {
  risk_score: "Risk",
  pv_score: "Present Value",
  capital_efficiency_score: "Capital Efficiency",
  purchasing_power_score: "Purchasing Power",
  robustness_score: "Robustness",
  consumption_ratio_score: "Consumption Ratio",
  stability_score: "Stability",
  legacy_score: "Legacy",
  coast_fire_score: "Coast FIRE",
  accumulation_velocity_score: "Accumulation Velocity",
  contribution_efficiency_score: "Contribution Efficiency",
  sharpe_ratio_score: "Sharpe Ratio",
  calmar_ratio_score: "Calmar Ratio",
  downside_stability_score: "Downside Stability",
  ulcer_index_score: "Ulcer Index",
};

export function categoryLabel(category: string | null): string {
  if (!category) return "—";
  return category
    .split("_")
    .map((w) => w[0] + w.slice(1).toLowerCase())
    .join(" ");
}

export function EntryCard({
  entry,
  profile,
  profileName,
}: {
  entry: Entry;
  profile: string;
  profileName: string;
}) {
  const [radar, setRadar] = useState<{
    data: Data[];
    layout: Partial<Layout>;
  } | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadRadar() {
    if (radar || loading) return;
    setLoading(true);
    try {
      const res = await fetch(
        `/api/bff/leaderboard/${entry.id}/radar?profile=${profile}`,
      );
      if (res.ok) {
        const body = await res.json();
        setRadar(body.figure);
      }
    } finally {
      setLoading(false);
    }
  }

  const subScores = Object.entries(entry.scores)
    .filter(([k, v]) => typeof v === "number" && k !== "excellence_score")
    .map(([k, v]) => ({ label: SCORE_LABELS[k] ?? k, value: v as number }));

  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex flex-wrap items-center gap-4">
          <span className="text-3xl">
            {MEDALS[entry.rank - 1] ?? `#${entry.rank}`}
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-semibold">
              ✨ {entry.strategy_name}
              {entry.is_custom && (
                <Badge variant="secondary" className="ml-2 align-middle">
                  community
                </Badge>
              )}
            </p>
            <p className="text-sm text-muted-foreground">
              Category: {categoryLabel(entry.category)}
              {entry.author ? ` · by ${entry.author}` : ""}
            </p>
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
              <div className="grid gap-6 md:grid-cols-2">
                <div className="flex flex-col gap-2">
                  {subScores.map((s) => (
                    <div key={s.label}>
                      <div className="mb-0.5 flex justify-between text-xs">
                        <span>{s.label}</span>
                        <span className="tabular-nums">
                          {s.value.toFixed(1)}
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-secondary">
                        <div
                          className="h-2 rounded-full bg-primary"
                          style={{ width: `${Math.min(100, s.value)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
                <div>
                  {radar ? (
                    <Chart
                      className="h-80"
                      data={radar.data}
                      layout={{ ...radar.layout, autosize: true, width: undefined }}
                    />
                  ) : (
                    <Skeleton className="h-80 w-full" />
                  )}
                </div>
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  );
}
