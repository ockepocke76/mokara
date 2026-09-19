import type { Metadata } from "next";
import Link from "next/link";

import { apiFetch } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
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

import {
  fmtMs,
  fmtTokens,
  fmtUsd,
  fmtWhen,
  operationLabel,
  type OperationRow,
  type StepStats,
  type Summary,
  type UserTotals,
} from "./model";

export const metadata: Metadata = { title: "Admin · LLM usage" };

const WINDOWS = [20, 100, 500];
const DAY_RANGES = [7, 30, 90];

function clamp(raw: string | undefined, allowed: number[], fallback: number) {
  const n = Number(raw);
  return allowed.includes(n) ? n : fallback;
}

// A non-OK API response must surface as a clear error, not as a crash on
// an unexpected JSON shape further down.
async function getJson<T>(path: string): Promise<T> {
  const res = await apiFetch(path);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

export default async function AdminLlmUsagePage({
  searchParams,
}: {
  searchParams: Promise<{ window?: string; days?: string }>;
}) {
  const params = await searchParams;
  const window = clamp(params.window, WINDOWS, 100); // latest-N operations
  const days = clamp(params.days, DAY_RANGES, 30);

  const [summary, { users }, { operations: recent }] = await Promise.all([
    getJson<Summary>(`/admin/llm-usage/summary?window=${window}&days=${days}`),
    getJson<{ users: UserTotals[] }>(`/admin/llm-usage/users?days=${days}`),
    getJson<{ operations: OperationRow[] }>(`/admin/llm-usage/operations?limit=25`),
  ]);

  const unpriced = summary.totals.by_operation.reduce(
    (acc, o) => acc + (o.unpriced_calls ?? 0),
    0,
  );
  const link = (w: number, d: number) => `/admin/llm-usage?window=${w}&days=${d}`;

  return (
    <div className="space-y-8">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">LLM cost</h2>
          <p className="text-sm text-muted-foreground">
            Every Gemini call, priced at that day&apos;s list rate (thinking tokens
            billed as output). Per-operation stats use the latest {window} runs of
            each type; totals cover the last {days} days.
          </p>
        </div>
        <div className="flex flex-wrap gap-4 text-sm">
          <span className="text-muted-foreground">
            Window:{" "}
            {WINDOWS.map((w) => (
              <Link
                key={w}
                href={link(w, days)}
                className={
                  w === window ? "font-medium text-foreground" : "hover:text-foreground"
                }
              >
                {w}{" "}
              </Link>
            ))}
          </span>
          <span className="text-muted-foreground">
            Period:{" "}
            {DAY_RANGES.map((d) => (
              <Link
                key={d}
                href={link(window, d)}
                className={
                  d === days ? "font-medium text-foreground" : "hover:text-foreground"
                }
              >
                {d}d{" "}
              </Link>
            ))}
          </span>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        <Card size="sm">
          <CardHeader>
            <CardDescription>Last {days} days</CardDescription>
            <CardTitle className="text-2xl">{fmtUsd(summary.totals.cost_usd)}</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            {summary.totals.by_operation.reduce((a, o) => a + o.operations, 0)} operations ·{" "}
            {summary.totals.by_operation.reduce((a, o) => a + o.calls, 0)} calls
          </CardContent>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>All time</CardDescription>
            <CardTitle className="text-2xl">
              {fmtUsd(summary.totals.all_time_cost_usd)}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            {summary.totals.all_time_calls} calls recorded
          </CardContent>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>Gemini list prices, USD per 1M tokens (in · out · cached)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-xs">
            {Object.entries(summary.prices).map(([model, p]) => (
              <div key={model} className="font-mono">
                <div>{model}</div>
                {p ? (
                  <div className="text-muted-foreground">
                    {p.input} · {p.output} · {p.cached}
                  </div>
                ) : (
                  <div className="text-destructive">no price entry</div>
                )}
              </div>
            ))}
            {unpriced > 0 && (
              <p className="pt-1 text-destructive">
                {unpriced} successful call{unpriced === 1 ? "" : "s"} in the period used a
                model with no price entry — add it to core/llm_pricing.py.
              </p>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="space-y-4">
        <h3 className="text-base font-semibold">Cost per operation</h3>
        {summary.operations.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No LLM calls recorded yet — run a strategy creation or a report with AI
            analysis and it will show up here.
          </p>
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            {summary.operations.map((op) => (
              <Card key={op.operation} size="sm">
                <CardHeader>
                  <CardTitle>{operationLabel(op.operation)}</CardTitle>
                  <CardDescription>
                    latest {op.n} · {fmtWhen(op.window_from)} → {fmtWhen(op.window_to)}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <dl className="grid grid-cols-4 gap-2 text-center">
                    <Stat label="median" value={fmtUsd(op.median_cost_usd)} strong />
                    <Stat label="mean" value={fmtUsd(op.mean_cost_usd)} />
                    <Stat label="p90" value={fmtUsd(op.p90_cost_usd)} />
                    <Stat label="max" value={fmtUsd(op.max_cost_usd)} />
                  </dl>
                  <p className="text-xs text-muted-foreground">
                    {op.mean_calls.toFixed(1)} calls · in {fmtTokens(op.mean_prompt_tokens)}
                    {op.mean_cached_tokens > 0 && ` (${fmtTokens(op.mean_cached_tokens)} cached)`}
                    {" "}· out {fmtTokens(op.mean_completion_tokens)} · thinking{" "}
                    {fmtTokens(op.mean_thinking_tokens)} · {fmtMs(op.mean_latency_ms)} LLM time
                    {op.failed_calls > 0 && (
                      <>
                        {" "}· <span className="text-destructive">{op.failed_calls} failed calls</span>
                      </>
                    )}
                  </p>
                  <StepsTable steps={summary.steps[op.operation] ?? []} />
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section className="grid gap-8 xl:grid-cols-[1fr_2fr]">
        <div className="space-y-3">
          <h3 className="text-base font-semibold">Spend by day</h3>
          {summary.totals.by_day.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing in the period.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Day</TableHead>
                  <TableHead className="text-right">Ops</TableHead>
                  <TableHead className="text-right">Cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...summary.totals.by_day].reverse().map((d) => (
                  <TableRow key={d.day}>
                    <TableCell className="font-mono text-xs">{d.day}</TableCell>
                    <TableCell className="text-right">{d.operations}</TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {fmtUsd(d.cost_usd)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        <div className="space-y-3">
          <h3 className="text-base font-semibold">By user (last {days} days)</h3>
          {users.length === 0 ? (
            <p className="text-sm text-muted-foreground">No usage in the period.</p>
          ) : (
            <Table className="text-xs">
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Tier</TableHead>
                  <TableHead className="text-right">Create</TableHead>
                  <TableHead className="text-right">Evolve</TableHead>
                  <TableHead className="text-right">Q&amp;A</TableHead>
                  <TableHead className="text-right">Report</TableHead>
                  <TableHead className="text-right">Cost</TableHead>
                  <TableHead>Last</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.user_id ?? "anon"}>
                    <TableCell>
                      {u.user_id != null ? (
                        <Link
                          href={`/admin/llm-usage/users/${u.user_id}`}
                          className="underline-offset-2 hover:underline"
                        >
                          {u.email ?? `#${u.user_id}`}
                        </Link>
                      ) : (
                        <span className="text-muted-foreground">(no user)</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {u.tier ? <Badge variant="outline">{u.tier}</Badge> : "—"}
                    </TableCell>
                    <TableCell className="text-right">{u.strategy_create}</TableCell>
                    <TableCell className="text-right">{u.strategy_evolve}</TableCell>
                    <TableCell className="text-right">{u.strategy_qa}</TableCell>
                    <TableCell className="text-right">{u.report_analysis}</TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {fmtUsd(u.cost_usd)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {fmtWhen(u.last_activity)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-base font-semibold">Recent operations</h3>
        {recent.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing recorded yet.</p>
        ) : (
          <Table className="text-xs">
            <TableHeader>
              <TableRow>
                <TableHead>Operation</TableHead>
                <TableHead>User</TableHead>
                <TableHead className="text-right">Calls</TableHead>
                <TableHead className="text-right">In</TableHead>
                <TableHead className="text-right">Out</TableHead>
                <TableHead className="text-right">Thinking</TableHead>
                <TableHead className="text-right">Cost</TableHead>
                <TableHead>Finished</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recent.map((r) => (
                <TableRow key={`${r.operation}:${r.ref_id}`}>
                  <TableCell>
                    <Link
                      href={`/admin/llm-usage/ops/${encodeURIComponent(r.operation)}/${encodeURIComponent(r.ref_id)}`}
                      className="underline-offset-2 hover:underline"
                    >
                      {operationLabel(r.operation)}
                    </Link>
                    {r.failed_calls > 0 && (
                      <Badge variant="destructive" className="ml-2">
                        {r.failed_calls} failed
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-xs">
                    {r.user_id != null ? (
                      <Link
                        href={`/admin/llm-usage/users/${r.user_id}`}
                        className="underline-offset-2 hover:underline"
                      >
                        {r.email ?? `#${r.user_id}`}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="text-right">{r.calls}</TableCell>
                  <TableCell className="text-right">{fmtTokens(r.prompt_tokens)}</TableCell>
                  <TableCell className="text-right">{fmtTokens(r.completion_tokens)}</TableCell>
                  <TableCell className="text-right">{fmtTokens(r.thinking_tokens)}</TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {fmtUsd(r.cost_usd)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {fmtWhen(r.finished_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  strong,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className={`font-mono ${strong ? "text-lg font-semibold" : "text-sm"}`}>{value}</dd>
    </div>
  );
}

function StepsTable({ steps }: { steps: StepStats[] }) {
  if (steps.length === 0) return null;
  return (
    <div className="overflow-x-auto">
      <Table className="text-xs">
        <TableHeader>
          <TableRow>
            <TableHead className="px-2">Step</TableHead>
            <TableHead className="px-2 text-right">Calls/op</TableHead>
            <TableHead className="px-2 text-right">In</TableHead>
            <TableHead className="px-2 text-right">Out</TableHead>
            <TableHead className="px-2 text-right">Think</TableHead>
            <TableHead className="px-2 text-right">$/op</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {steps.map((s) => (
            <TableRow key={`${s.step}:${s.tier}`}>
              <TableCell className="px-2 font-mono">
                {s.step}
                {s.tier && (
                  <span className="ml-1 font-sans text-muted-foreground">{s.tier}</span>
                )}
              </TableCell>
              <TableCell className="px-2 text-right">{s.calls_per_operation.toFixed(2)}</TableCell>
              <TableCell className="px-2 text-right">{fmtTokens(s.mean_prompt_tokens)}</TableCell>
              <TableCell className="px-2 text-right">{fmtTokens(s.mean_completion_tokens)}</TableCell>
              <TableCell className="px-2 text-right">{fmtTokens(s.mean_thinking_tokens)}</TableCell>
              <TableCell className="px-2 text-right font-mono">
                {fmtUsd(s.cost_per_operation_usd)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
