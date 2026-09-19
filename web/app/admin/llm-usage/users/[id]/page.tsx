import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { apiFetch } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import {
  Card,
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
} from "../../model";

export const metadata: Metadata = { title: "Admin · LLM usage · user" };

type Detail = {
  user: { id: number; email: string; name: string | null; tier: string };
  summary: {
    all_time_cost_usd: number;
    cost_30d_usd: number;
    cost_month_usd: number;
    operations: number;
    operations_month: number;
  };
  operations: OperationRow[];
};

export default async function AdminLlmUsageUserPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const res = await apiFetch(`/admin/llm-usage/users/${id}?limit=100`);
  if (res.status === 404) notFound();
  const detail: Detail = await res.json();
  const { user, summary, operations } = detail;

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/admin/llm-usage"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← LLM usage
        </Link>
        <h2 className="mt-2 text-lg font-semibold">
          {user.email}{" "}
          <Badge variant="outline" className="ml-2 align-middle">
            {user.tier}
          </Badge>
        </h2>
        {user.name && <p className="text-sm text-muted-foreground">{user.name}</p>}
      </div>

      <section className="grid gap-4 sm:grid-cols-3">
        <Card size="sm">
          <CardHeader>
            <CardDescription>This month</CardDescription>
            <CardTitle className="text-2xl">{fmtUsd(summary.cost_month_usd)}</CardTitle>
            <CardDescription>{summary.operations_month} operations</CardDescription>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>Last 30 days</CardDescription>
            <CardTitle className="text-2xl">{fmtUsd(summary.cost_30d_usd)}</CardTitle>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>All time</CardDescription>
            <CardTitle className="text-2xl">{fmtUsd(summary.all_time_cost_usd)}</CardTitle>
            <CardDescription>{summary.operations} operations</CardDescription>
          </CardHeader>
        </Card>
      </section>

      <section className="space-y-3">
        <h3 className="text-base font-semibold">Operations</h3>
        {operations.length === 0 ? (
          <p className="text-sm text-muted-foreground">No LLM usage recorded for this user.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Operation</TableHead>
                <TableHead className="text-right">Calls</TableHead>
                <TableHead className="text-right">In</TableHead>
                <TableHead className="text-right">Out</TableHead>
                <TableHead className="text-right">Thinking</TableHead>
                <TableHead className="text-right">LLM time</TableHead>
                <TableHead className="text-right">Cost</TableHead>
                <TableHead>Finished</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {operations.map((o) => (
                <TableRow key={`${o.operation}:${o.ref_id}`}>
                  <TableCell>
                    <Link
                      href={`/admin/llm-usage/ops/${encodeURIComponent(o.operation)}/${encodeURIComponent(o.ref_id)}`}
                      className="underline-offset-2 hover:underline"
                    >
                      {operationLabel(o.operation)}
                    </Link>
                    {o.failed_calls > 0 && (
                      <Badge variant="destructive" className="ml-2">
                        {o.failed_calls} failed
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right">{o.calls}</TableCell>
                  <TableCell className="text-right">{fmtTokens(o.prompt_tokens)}</TableCell>
                  <TableCell className="text-right">{fmtTokens(o.completion_tokens)}</TableCell>
                  <TableCell className="text-right">{fmtTokens(o.thinking_tokens)}</TableCell>
                  <TableCell className="text-right">{fmtMs(o.latency_ms)}</TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {fmtUsd(o.cost_usd)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {fmtWhen(o.finished_at)}
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
