"use client";

/**
 * Presentational cards for the designer build log. Pedagogic rules from
 * W5_DESIGNER_UX.md: plain language first, code collapsed, assumptions
 * visually distinct, 10-path uncertainty labeled, neutral baseline framing.
 */
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Chart } from "@/components/chart";

import {
  AnalyzeArtifact,
  CheckItem,
  RunModel,
  Spec,
  TestArtifact,
  TestPath,
  fmtCompact,
  fmtPercent,
} from "../model";

const CATEGORY_LABELS: Record<string, string> = {
  WITHDRAWAL_ONLY: "Withdrawal",
  CONTRIBUTION_ONLY: "Contribution",
  HYBRID: "Hybrid",
};

export function SpecCard({ spec, strategyName }: { spec: Spec; strategyName?: string }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          Here&apos;s what I understood
          {spec.category && (
            <Badge variant="secondary">
              {CATEGORY_LABELS[spec.category] ?? spec.category}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {strategyName && (
          <p>
            Working name: <span className="font-medium">{strategyName}</span>
          </p>
        )}
        {spec.summary && <p>{spec.summary}</p>}
        {!!spec.mechanics?.length && (
          <ul className="list-disc space-y-1 pl-5">
            {spec.mechanics.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        )}
        {!!spec.constraints?.length && (
          <p className="text-muted-foreground">
            Hard constraints: {spec.constraints.join("; ")}
          </p>
        )}
        {!!spec.assumptions?.length && (
          <div className="rounded-md border border-dashed p-3">
            <p className="mb-1 text-xs font-medium uppercase text-muted-foreground">
              Assumed (change at review if wrong)
            </p>
            <ul className="list-disc space-y-1 pl-5">
              {spec.assumptions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </div>
        )}
        {!!spec.proposed_parameters?.length && (
          <p className="text-muted-foreground">
            Tunable parameters:{" "}
            {spec.proposed_parameters
              .map((p) => `${p.name} (${p.default ?? "?"})`)
              .join(", ")}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export function ExamplesCard({ examples }: { examples: NonNullable<RunModel["examples"]> }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          {examples.length
            ? `Drawing on ${examples.length} reference ${examples.length === 1 ? "strategy" : "strategies"}`
            : "No close matches — building from the base playbook"}
        </CardTitle>
      </CardHeader>
      {!!examples.length && (
        <CardContent className="flex flex-wrap gap-2">
          {examples.map((e) => (
            <Badge key={e.name} variant="outline" className="gap-1">
              {e.name}
              <span className="text-muted-foreground">
                · {e.source === "builtin" ? "built-in" : "community"}
              </span>
            </Badge>
          ))}
        </CardContent>
      )}
    </Card>
  );
}

export function BlueprintCard({ plan }: { plan: NonNullable<RunModel["plan"]> }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">The blueprint</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <ol className="list-decimal space-y-1.5 pl-5">
          {(plan.rules ?? []).map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ol>
        {!!plan.parameters?.length && (
          <p className="text-muted-foreground">
            Parameters:{" "}
            {plan.parameters
              .map((p) => `${p.name} (default ${p.default ?? "?"})`)
              .join(", ")}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export function CodeCard({
  code,
  description,
  isEvolution,
}: {
  code: string;
  description?: string;
  isEvolution?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const lines = code.split("\n").length;
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          The strategy{isEvolution ? " (evolved)" : ""}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {description && <p>{description}</p>}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-xs text-muted-foreground underline underline-offset-2"
        >
          {open ? "Hide the Python" : `View the Python — ${lines} lines`}
        </button>
        {open && (
          <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs leading-5">
            <code>{code}</code>
          </pre>
        )}
      </CardContent>
    </Card>
  );
}

const CHECK_LABELS: Record<string, string> = {
  sandbox: "Compiles and dry-runs in the sandbox (untrusted-code jail)",
  blueprint_conformance: "Code implements the blueprint",
};

export function ChecksCard({
  checks,
  attemptNote,
}: {
  checks: CheckItem[];
  attemptNote?: string | null;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Safety checks</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {checks.map((c) => (
          <div key={c.check}>
            <p>
              <span className={c.passed ? "text-emerald-600" : "text-red-600"}>
                {c.passed ? "✓" : "✗"}
              </span>{" "}
              {CHECK_LABELS[c.check] ?? c.check}
            </p>
            {!c.passed && c.message && (
              <details className="ml-5 mt-1 text-xs text-muted-foreground">
                <summary>What failed</summary>
                <pre className="mt-1 whitespace-pre-wrap">{c.message}</pre>
              </details>
            )}
            {!!c.rule_verdicts?.length && (
              <ul className="ml-5 mt-1 space-y-0.5 text-xs text-muted-foreground">
                {c.rule_verdicts.map((v, i) => (
                  <li key={i}>
                    {v.implemented ? "✓" : "✗"} {v.rule}
                    {v.note ? ` — ${v.note}` : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
        {attemptNote && (
          <p className="text-xs text-amber-600">{attemptNote}</p>
        )}
      </CardContent>
    </Card>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}

type SeriesKey =
  | "net_worth"
  | "asset_value"
  | "debt"
  | "cash"
  | "contributed"
  | "withdrawn"
  | "borrowed"
  | "sold";

/** Thin lines for the random paths, one thick highlighted line for the
 * historical backtest — the same visual grammar as the old app's test UI. */
function seriesTraces(
  paths: TestPath[],
  key: SeriesKey,
  color: string,
  backtestColor: string,
) {
  const traces = [];
  let firstRandom = true;
  for (const p of paths) {
    const y = p[key];
    if (!y || !y.length) continue;
    if (p.is_backtest) {
      traces.push({
        x: p.years,
        y,
        type: "scatter" as const,
        mode: "lines" as const,
        line: { width: 3, color: backtestColor },
        name: p.label || "Historical backtest",
      });
    } else {
      traces.push({
        x: p.years,
        y,
        type: "scatter" as const,
        mode: "lines" as const,
        line: { width: 1, color },
        name: "Test paths",
        showlegend: firstRandom,
        hoverinfo: "skip" as const,
      });
      firstRandom = false;
    }
  }
  return traces;
}

function SeriesChart({
  paths,
  seriesKey,
  title,
  color,
  backtestColor,
  className = "h-64",
}: {
  paths: TestPath[];
  seriesKey: SeriesKey;
  title: string;
  color: string;
  backtestColor: string;
  className?: string;
}) {
  const traces = seriesTraces(paths, seriesKey, color, backtestColor);
  if (!traces.length) return null;
  return (
    <Chart
      className={className}
      data={traces}
      layout={{
        yaxis: { tickformat: ".3s", title: { text: title } },
        xaxis: { title: { text: "Year" } },
        showlegend: false,
      }}
    />
  );
}

const num = (v: unknown): number | null => (typeof v === "number" ? v : null);
const fmtOrDash = (v: number | null | undefined) =>
  typeof v === "number" ? fmtCompact.format(v) : "—";

const TABLE_COLUMNS: { key: SeriesKey; label: string }[] = [
  { key: "net_worth", label: "Net worth" },
  { key: "asset_value", label: "Assets" },
  { key: "cash", label: "Cash" },
  { key: "debt", label: "Debt" },
  { key: "contributed", label: "Contributed" },
  { key: "withdrawn", label: "Withdrawn" },
  // Raw signed engine value (draws minus repayments) — "Debt change" reads
  // correctly whichever way it goes; the chart below splits it into two
  // always-nonnegative bars instead.
  { key: "borrowed", label: "Debt change" },
  { key: "sold", label: "Sold" },
];

function YearByYearTable({ paths }: { paths: TestPath[] }) {
  const backtestIdx = paths.findIndex((p) => p.is_backtest);
  const [selected, setSelected] = useState(
    String(backtestIdx >= 0 ? backtestIdx : 0),
  );
  const path = paths[Number(selected)] ?? paths[0];
  const columns = TABLE_COLUMNS.filter((c) => path[c.key]?.length);
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-xs text-muted-foreground underline underline-offset-2">
        Year-by-year detail
      </summary>
      <div className="mt-3 space-y-2">
        <Select value={selected} onValueChange={setSelected}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {paths.map((p, i) => (
              <SelectItem key={i} value={String(i)}>
                {p.label || `Path ${i + 1}`}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="max-h-80 overflow-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Year</TableHead>
                {columns.map((c) => (
                  <TableHead key={c.key} className="text-right">
                    {c.label}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {path.years.map((year, i) => (
                <TableRow key={year}>
                  <TableCell>{year}</TableCell>
                  {columns.map((c) => (
                    <TableCell key={c.key} className="text-right tabular-nums">
                      {fmtOrDash(path[c.key]?.[i])}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </details>
  );
}

export function TestFlightCard({ test }: { test: TestArtifact }) {
  const s = test.summary_stats ?? {};
  const baseline = test.baseline;
  const paths = test.paths ?? [];
  // Older persisted runs condensed only net worth; hide the extra views then.
  const hasExtras = paths.some((p) => p.asset_value?.length);
  const backtest = paths.find((p) => p.is_backtest);

  const category = typeof s.strategy_category === "string" ? s.strategy_category : null;
  const contributed = num(s.backtest_total_contributed);
  const withdrawn = num(s.backtest_total_withdrawn);
  const taxes = num(s.backtest_total_taxes);
  const fees = num(s.backtest_total_fees);
  const costs = taxes !== null || fees !== null ? (taxes ?? 0) + (fees ?? 0) : null;
  // Highest debt across every shipped path, backtest included — the summary
  // stat covers random paths only, which would contradict the debt chart.
  const pathPeakDebt = paths
    .flatMap((p) => p.debt ?? [])
    .reduce<number | null>((m, v) => (typeof v === "number" && (m === null || v > m) ? v : m), null);
  const peakDebt = pathPeakDebt ?? num(s.max_debt_across_paths);
  // A zero tile is noise, not a finding — every tile requires a positive value.
  const backtestTiles = [
    contributed !== null && contributed > 0
      ? { label: "Total contributed", value: fmtCompact.format(contributed) }
      : null,
    withdrawn !== null && withdrawn > 0
      ? { label: "Total withdrawn", value: fmtCompact.format(withdrawn) }
      : null,
    costs !== null && costs > 0
      ? { label: "Taxes & fees paid", value: fmtCompact.format(costs) }
      : null,
  ].filter((t) => t !== null);
  const flowTiles = [
    ...backtestTiles,
    ...(peakDebt !== null && peakDebt > 0
      ? [{ label: "Peak debt", value: fmtCompact.format(peakDebt) }]
      : []),
  ];
  const flowCaption = [
    backtestTiles.length ? "Cash totals are from the historical backtest." : null,
    peakDebt !== null && peakDebt > 0
      ? "Peak debt is the highest debt reached across all test paths."
      : null,
  ]
    .filter(Boolean)
    .join(" ");

  // Debt-funded strategies (e.g. Buy Borrow Die) show zero withdrawn —
  // spending shows up as borrowing/asset sales instead. 'borrowed' is the
  // engine's signed net debt change (draws minus repayments), so it's split
  // into two always-nonnegative bars here rather than plotting a value that
  // can go negative under a one-directional "Borrowed" label/color.
  const FLOW_SERIES = backtest
    ? (
        [
          { name: "Contributed", captionLabel: "contributions", color: "rgba(44,160,44,0.7)", values: backtest.contributed },
          { name: "Withdrawn", captionLabel: "withdrawals", color: "rgba(214,39,40,0.7)", values: backtest.withdrawn },
          {
            name: "Borrowed",
            captionLabel: "borrowing",
            color: "rgba(255,127,14,0.7)",
            values: backtest.borrowed?.map((v) => ((v ?? 0) > 0 ? v : 0)),
          },
          {
            name: "Debt repaid",
            captionLabel: "debt repayment",
            color: "rgba(31,119,180,0.7)",
            values: backtest.borrowed?.map((v) => ((v ?? 0) < 0 ? -(v ?? 0) : 0)),
          },
          { name: "Sold", captionLabel: "asset sales", color: "rgba(148,103,189,0.7)", values: backtest.sold },
        ] satisfies { name: string; captionLabel: string; color: string; values: (number | null)[] | undefined }[]
      ).filter((s) => s.values?.some((v) => (v ?? 0) !== 0))
    : [];

  const cashFlowBars = backtest
    ? FLOW_SERIES.map((s) => ({
        x: backtest.years,
        y: s.values,
        type: "bar" as const,
        name: s.name,
        marker: { color: s.color },
      }))
    : [];

  const flowCaptionText = FLOW_SERIES.length
    ? `Annual ${new Intl.ListFormat("en", { style: "long", type: "conjunction" }).format(
        FLOW_SERIES.map((s) => s.captionLabel),
      )} along the historical backtest path.`
    : "";

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          Test flight
          {category && CATEGORY_LABELS[category] && (
            <Badge variant="secondary">{CATEGORY_LABELS[category]}</Badge>
          )}
          <Badge variant="outline">
            {test.num_paths ?? 10} markets × {test.num_years ?? 30} years — checks
            behavior, not performance
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <StatTile label="Success rate" value={fmtPercent(s.success_rate)} />
          <StatTile
            label="Median final net worth"
            value={fmtOrDash(num(s.median_final_net_worth))}
          />
          <StatTile
            label="Worst path final"
            value={fmtOrDash(num(s.worst_final_nw))}
          />
          <StatTile
            label="Backtest max drawdown"
            value={fmtPercent(s.backtest_max_drawdown)}
          />
        </div>
        {!!flowTiles.length && (
          <div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {flowTiles.map((t) => (
                <StatTile key={t.label} label={t.label} value={t.value} />
              ))}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{flowCaption}</p>
          </div>
        )}
        {!hasExtras ? (
          <SeriesChart
            paths={paths}
            seriesKey="net_worth"
            title="Net worth"
            color="rgba(100,150,200,0.4)"
            backtestColor="rgb(255,127,14)"
          />
        ) : (
          <Tabs defaultValue="net_worth">
            <TabsList>
              <TabsTrigger value="net_worth">Net worth</TabsTrigger>
              <TabsTrigger value="balance">Assets, cash &amp; debt</TabsTrigger>
              <TabsTrigger value="flows">Cash flows</TabsTrigger>
            </TabsList>
            <TabsContent value="net_worth" className="mt-2">
              <SeriesChart
                paths={paths}
                seriesKey="net_worth"
                title="Net worth"
                color="rgba(100,150,200,0.4)"
                backtestColor="rgb(255,127,14)"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Thin lines are the simulated markets
                {backtest ? "; the thick line is the historical backtest" : ""}.
              </p>
            </TabsContent>
            <TabsContent value="balance" className="mt-2">
              <div className="grid gap-3 sm:grid-cols-2">
                <SeriesChart
                  className="h-48"
                  paths={paths}
                  seriesKey="asset_value"
                  title="Asset value"
                  color="rgba(50,200,100,0.35)"
                  backtestColor="rgb(44,160,44)"
                />
                <SeriesChart
                  className="h-48"
                  paths={paths}
                  seriesKey="cash"
                  title="Cash balance"
                  color="rgba(150,120,220,0.35)"
                  backtestColor="rgb(110,70,200)"
                />
                <SeriesChart
                  className="h-48"
                  paths={paths}
                  seriesKey="debt"
                  title="Debt"
                  color="rgba(200,50,50,0.35)"
                  backtestColor="rgb(214,39,40)"
                />
              </div>
            </TabsContent>
            <TabsContent value="flows" className="mt-2">
              {cashFlowBars.length ? (
                <>
                  <Chart
                    className="h-64"
                    data={cashFlowBars}
                    layout={{
                      barmode: "group",
                      yaxis: { tickformat: ".3s", title: { text: "Annual amount" } },
                      xaxis: { title: { text: "Year" } },
                    }}
                  />
                  <p className="mt-1 text-xs text-muted-foreground">{flowCaptionText}</p>
                </>
              ) : (
                <p className="py-6 text-center text-xs text-muted-foreground">
                  {backtest
                    ? "No contributions, withdrawals, borrowing, debt repayment, or asset sales occurred on the backtest path."
                    : "This run produced no historical backtest path to chart cash flows from."}
                </p>
              )}
            </TabsContent>
          </Tabs>
        )}
        {hasExtras && !!paths.length && (
          // Re-key on the path list shape so a re-run with a different path
          // count (e.g. a missing backtest) resets the stale selection.
          <YearByYearTable key={paths.length} paths={paths} />
        )}
        {baseline && (
          <p className="text-xs text-muted-foreground">
            On the exact same {test.num_paths ?? 10} markets,{" "}
            <span className="font-medium">{baseline.name}</span> scored: success
            rate {fmtPercent(baseline.summary_stats?.success_rate)}, median final{" "}
            {typeof baseline.summary_stats?.median_final_net_worth === "number"
              ? fmtCompact.format(baseline.summary_stats.median_final_net_worth)
              : "—"}
            . {test.num_paths ?? 10} paths are noisy — the full evaluation is the
            fair test.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export function BehaviorCard({ analyze }: { analyze: AnalyzeArtifact }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          How it behaves
          {analyze.conforms_to_spec !== undefined && (
            <Badge variant={analyze.conforms_to_spec ? "secondary" : "destructive"}>
              {analyze.conforms_to_spec
                ? "matches the blueprint"
                : "did not match the blueprint"}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {analyze.typical_year && (
          <p>
            <span className="font-medium">In a typical year: </span>
            {analyze.typical_year}
          </p>
        )}
        {analyze.worst_path_story && (
          <p>
            <span className="font-medium">In the worst test path: </span>
            {analyze.worst_path_story}
          </p>
        )}
        {!!analyze.mismatches?.length && (
          <ul className="list-disc pl-5 text-red-600">
            {analyze.mismatches.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        )}
        {analyze.notes && (
          <p className="text-xs text-muted-foreground">{analyze.notes}</p>
        )}
      </CardContent>
    </Card>
  );
}
