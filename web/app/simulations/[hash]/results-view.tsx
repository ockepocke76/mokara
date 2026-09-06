"use client";

import ReactMarkdown from "react-markdown";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Chart } from "@/components/chart";

type DfSeries = { index: (string | number)[]; series: Record<string, number[]> };

export type SimulationResults = {
  simulation_hash: string;
  params: Record<string, string | number | null>;
  stats: Record<string, unknown>;
  gemini_content?: {
    analysis?: string;
    main_outcome?: string;
    bottom_line?: string;
  } | null;
  charts: {
    net_worth_percentile_paths: DfSeries | null;
    asset_percentile_paths: DfSeries | null;
    sampled_paths: DfSeries | null;
    final_net_worths_hist: { counts: number[]; bin_edges: number[] } | null;
    median_yearly_results: DfSeries | null;
  };
};

const ACCENT = "#171717";

function fmtMoney(v: unknown, currency?: string | number | null): string {
  if (typeof v !== "number") return "—";
  return `${Math.round(v).toLocaleString()} ${currency ?? ""}`.trim();
}

function fmtPct(v: unknown): string {
  if (typeof v !== "number") return "—";
  return `${(v * 100).toFixed(1)}%`;
}

export function ResultsView({ results }: { results: SimulationResults }) {
  const { params, stats, charts } = results;
  const currency = params.currency;

  const fan = charts.net_worth_percentile_paths;
  const sampled = charts.sampled_paths;
  const hist = charts.final_net_worths_hist;
  const yearly = charts.median_yearly_results;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">
          {params.simulation_name || "Simulation results"}
        </h1>
        <p className="text-sm text-muted-foreground">
          {String(params.custom_strategy_name ?? params.strategy)} ·{" "}
          {String(params.asset_name ?? params.asset_model)} ·{" "}
          {String(params.num_years)} years ·{" "}
          {Number(params.num_simulations).toLocaleString()} runs ·{" "}
          {fmtMoney(params.initial_investment, currency)} initial
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Success rate"
          value={fmtPct(stats.success_rate)}
        />
        <StatCard
          label="Chance of ruin"
          value={fmtPct(stats.chance_of_ruin)}
        />
        <StatCard
          label="Median final net worth"
          value={fmtMoney(stats.median_final_net_worth, currency)}
        />
        <StatCard
          label="Median total withdrawn"
          value={fmtMoney(stats.median_total_withdrawn, currency)}
        />
      </div>

      {fan && (
        <Card>
          <CardHeader>
            <CardTitle>Net worth over time</CardTitle>
            <CardDescription>
              Median with 25th–75th percentile band
              {sampled ? "; sampled individual paths in grey" : ""}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Chart
              className="h-96"
              data={[
                ...(sampled
                  ? Object.entries(sampled.series).map(([name, ys]) => ({
                      type: "scatter" as const,
                      mode: "lines" as const,
                      x: sampled.index,
                      y: ys,
                      line: { color: "rgba(120,120,120,0.15)", width: 1 },
                      hoverinfo: "skip" as const,
                      showlegend: false,
                      name,
                    }))
                  : []),
                {
                  type: "scatter",
                  mode: "lines",
                  x: fan.index,
                  y: fan.series.p25,
                  line: { width: 0 },
                  showlegend: false,
                  name: "p25",
                },
                {
                  type: "scatter",
                  mode: "lines",
                  x: fan.index,
                  y: fan.series.p75,
                  fill: "tonexty",
                  fillcolor: "rgba(23,23,23,0.12)",
                  line: { width: 0 },
                  showlegend: false,
                  name: "p75",
                },
                {
                  type: "scatter",
                  mode: "lines",
                  x: fan.index,
                  y: fan.series.p50,
                  line: { color: ACCENT, width: 2.5 },
                  name: "Median",
                },
              ]}
              layout={{
                xaxis: { title: { text: "Year" } },
                yaxis: {
                  title: { text: `Net worth (${currency ?? ""})` },
                  type: "log",
                },
                showlegend: false,
              }}
            />
          </CardContent>
        </Card>
      )}

      {hist?.counts && hist?.bin_edges && (
        <Card>
          <CardHeader>
            <CardTitle>Distribution of final outcomes</CardTitle>
            <CardDescription>
              Final net worth across all {Number(params.num_simulations).toLocaleString()} runs
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Chart
              className="h-72"
              data={[
                {
                  type: "bar",
                  x: hist.bin_edges.slice(0, hist.counts.length),
                  y: hist.counts,
                  marker: { color: ACCENT },
                },
              ]}
              layout={{
                bargap: 0.05,
                xaxis: { title: { text: `Final net worth (${currency ?? ""})` } },
                yaxis: { title: { text: "Simulations" } },
              }}
            />
          </CardContent>
        </Card>
      )}

      {yearly && (
        <Card>
          <CardHeader>
            <CardTitle>Median yearly breakdown</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Year</TableHead>
                  {Object.keys(yearly.series).map((c) => (
                    <TableHead key={c} className="text-right">
                      {c}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {yearly.index.map((year, i) => (
                  <TableRow key={String(year)}>
                    <TableCell>{String(year)}</TableCell>
                    {Object.values(yearly.series).map((col, j) => (
                      <TableCell key={j} className="text-right tabular-nums">
                        {typeof col[i] === "number"
                          ? Math.round(col[i]).toLocaleString()
                          : String(col[i] ?? "—")}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <AiAnalysis content={results.gemini_content} />
    </div>
  );
}

function AiAnalysis({
  content,
}: {
  content: SimulationResults["gemini_content"];
}) {
  const sections = [
    { title: "Bottom line", text: content?.bottom_line },
    { title: "Main outcome", text: content?.main_outcome },
    { title: "Analysis", text: content?.analysis },
  ].filter(
    (s): s is { title: string; text: string } =>
      typeof s.text === "string" &&
      s.text.length > 0 &&
      s.text !== "Analysis was disabled.",
  );
  if (sections.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>AI analysis</CardTitle>
      </CardHeader>
      <CardContent className="prose prose-neutral dark:prose-invert max-w-none text-sm">
        {sections.map((s) => (
          <section key={s.title}>
            <h3>{s.title}</h3>
            <ReactMarkdown>{s.text}</ReactMarkdown>
          </section>
        ))}
      </CardContent>
    </Card>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl tabular-nums">{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}
