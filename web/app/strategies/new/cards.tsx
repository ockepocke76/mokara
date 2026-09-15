"use client";

/**
 * Presentational cards for the designer build log. Pedagogic rules from
 * W5_DESIGNER_UX.md: plain language first, code collapsed, assumptions
 * visually distinct, 10-path uncertainty labeled, neutral baseline framing.
 */
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Chart } from "@/components/chart";

import {
  AnalyzeArtifact,
  CheckItem,
  RunModel,
  Spec,
  TestArtifact,
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
        {!!spec.changes?.length && (
          <div className="rounded-md border p-3">
            <p className="mb-1 text-xs font-medium uppercase text-muted-foreground">
              What will change
              {spec.change_scope === "parameter_only"
                ? " — parameter values only"
                : spec.change_scope === "structural"
                  ? " — a full redesign"
                  : ""}
            </p>
            <ul className="list-disc space-y-1 pl-5">
              {spec.changes.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
            {spec.change_scope !== "structural" && (
              <p className="mt-1 text-xs text-muted-foreground">
                Everything else stays exactly as it is.
              </p>
            )}
          </div>
        )}
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
  const seedOnly = examples.length === 1 && examples[0].source === "seed";
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          {seedOnly
            ? "Working from the current version — no outside examples"
            : examples.length
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
                ·{" "}
                {e.source === "seed"
                  ? "the strategy being evolved"
                  : e.source === "builtin"
                    ? "built-in"
                    : "community"}
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

function DiffView({ diff }: { diff: string }) {
  return (
    <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs leading-5">
      {diff.split("\n").map((line, i) => {
        const kind = line.startsWith("+++") || line.startsWith("---")
          ? "meta"
          : line.startsWith("+")
            ? "add"
            : line.startsWith("-")
              ? "del"
              : line.startsWith("@@")
                ? "hunk"
                : "ctx";
        const cls =
          kind === "add"
            ? "block bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
            : kind === "del"
              ? "block bg-red-500/15 text-red-700 dark:text-red-400"
              : kind === "hunk" || kind === "meta"
                ? "block text-muted-foreground"
                : "block";
        return (
          <code key={i} className={cls}>
            {line || " "}
          </code>
        );
      })}
    </pre>
  );
}

export function CodeCard({
  code,
  description,
  isEvolution,
  diff,
}: {
  code: string;
  description?: string;
  isEvolution?: boolean;
  diff?: string;
}) {
  const [open, setOpen] = useState(false);
  const [diffOpen, setDiffOpen] = useState(false);
  const lines = code.split("\n").length;
  const changedLines = diff
    ? diff
        .split("\n")
        .filter(
          (l) =>
            (l.startsWith("+") || l.startsWith("-")) &&
            !l.startsWith("+++") &&
            !l.startsWith("---"),
        ).length
    : 0;
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          The strategy{isEvolution ? " (evolved)" : ""}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {description && <p>{description}</p>}
        <div className="flex flex-wrap gap-4">
          {isEvolution && diff && (
            <button
              type="button"
              onClick={() => setDiffOpen((v) => !v)}
              className="text-xs text-muted-foreground underline underline-offset-2"
            >
              {diffOpen
                ? "Hide the changes"
                : changedLines
                  ? `View the changes — ${changedLines} line${changedLines === 1 ? "" : "s"}`
                  : "No lines changed"}
            </button>
          )}
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="text-xs text-muted-foreground underline underline-offset-2"
          >
            {open ? "Hide the Python" : `View the Python — ${lines} lines`}
          </button>
        </div>
        {diffOpen && diff && <DiffView diff={diff} />}
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
  minimal_change: "Only the requested change was made",
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

export function TestFlightCard({ test }: { test: TestArtifact }) {
  const s = test.summary_stats ?? {};
  const baseline = test.baseline;
  const traces = (test.paths ?? []).map((p, i) => ({
    x: p.years,
    y: p.net_worth,
    type: "scatter" as const,
    mode: "lines" as const,
    line: { width: 1, color: "rgba(100,150,200,0.4)" },
    name: "Test paths",
    showlegend: i === 0,
    hoverinfo: "skip" as const,
  }));
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          Test flight
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
            value={
              typeof s.median_final_net_worth === "number"
                ? fmtCompact.format(s.median_final_net_worth)
                : "—"
            }
          />
          <StatTile
            label="Worst path final"
            value={
              typeof s.worst_final_nw === "number"
                ? fmtCompact.format(s.worst_final_nw)
                : "—"
            }
          />
          <StatTile
            label="Backtest max drawdown"
            value={fmtPercent(s.backtest_max_drawdown)}
          />
        </div>
        {!!traces.length && (
          <Chart
            className="h-64"
            data={traces}
            layout={{
              yaxis: { tickformat: ".3s", title: { text: "Net worth" } },
              xaxis: { title: { text: "Year" } },
              showlegend: false,
            }}
          />
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
