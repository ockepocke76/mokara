"use client";

/** Shared evaluation-result fragments: the radar + component-score grid and
 *  the per-scenario table, rendered identically on the leaderboard entry
 *  details and the strategy page's Evaluation tab (R5.4 — they used to be
 *  near-identical copies). */
import type { Data, Layout } from "plotly.js";

import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Chart } from "@/components/chart";

export type MetricCell = {
  key: string;
  name: string;
  score: number;
  weight: number;
};

export type ScenarioRow = {
  name: string;
  sortino_ratio?: number | null;
  success_rate?: number | null;
};

export type RadarFigure = { data: Data[]; layout: Partial<Layout> };

export function EvaluationRadarScores({
  radar,
  metricGrid,
  profileName,
}: {
  radar: RadarFigure | null | undefined;
  metricGrid: MetricCell[];
  /** Shown after the weight percentage, e.g. "42% weight (Balanced)". */
  profileName?: string;
}) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
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
      <div>
        <p className="mb-2 text-sm font-semibold">🎯 Component Scores</p>
        <div className="grid grid-cols-2 gap-3">
          {metricGrid.map((m) => (
            <div key={m.key} className="leading-tight">
              <p className="text-xs text-muted-foreground">{m.name}</p>
              <p className="text-lg font-bold tabular-nums">
                {m.score.toFixed(0)}
              </p>
              <p className="text-[11px] text-muted-foreground">
                {m.weight > 0
                  ? `${(m.weight * 100).toFixed(0)}% weight${profileName ? ` (${profileName})` : ""}`
                  : "Informational"}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function ScenarioTable({
  scenarios,
  title = "Performance by scenario",
}: {
  scenarios: ScenarioRow[];
  title?: string;
}) {
  if (scenarios.length === 0) return null;
  return (
    <div>
      <p className="mb-2 text-sm font-semibold">{title}</p>
      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Scenario</TableHead>
              <TableHead className="text-right">Sortino Ratio</TableHead>
              <TableHead className="text-right">Success Rate</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {scenarios.map((s) => (
              <TableRow key={s.name}>
                <TableCell className="text-sm">{s.name}</TableCell>
                <TableCell className="text-right text-sm tabular-nums">
                  {s.sortino_ratio?.toFixed(2) ?? "—"}
                </TableCell>
                <TableCell className="text-right text-sm tabular-nums">
                  {s.success_rate !== null && s.success_rate !== undefined
                    ? `${(s.success_rate * 100).toFixed(1)}%`
                    : "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
