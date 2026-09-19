import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { apiFetch } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
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
  operationLabel,
  type CallRow,
} from "../../../model";

export const metadata: Metadata = { title: "Admin · LLM usage · operation" };

type Detail = {
  operation: string;
  ref_id: string;
  cost_usd: number;
  calls: CallRow[];
};

export default async function AdminLlmUsageOperationPage({
  params,
}: {
  params: Promise<{ operation: string; ref: string }>;
}) {
  const { operation, ref } = await params;
  const res = await apiFetch(
    `/admin/llm-usage/operations/${encodeURIComponent(operation)}/${encodeURIComponent(ref)}`,
  );
  if (res.status === 404) notFound();
  const detail: Detail = await res.json();
  const userId = detail.calls.find((c) => c.user_id != null)?.user_id ?? null;
  const isRun = operation === "strategy_create" || operation === "strategy_evolve";

  return (
    <div className="space-y-6">
      <div>
        <Link
          href={userId != null ? `/admin/llm-usage/users/${userId}` : "/admin/llm-usage"}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← back
        </Link>
        <h2 className="mt-2 text-lg font-semibold">
          {operationLabel(detail.operation)}{" "}
          <span className="font-mono text-sm font-normal text-muted-foreground">
            {detail.ref_id}
          </span>
        </h2>
        <p className="text-sm text-muted-foreground">
          {detail.calls.length} calls · {fmtUsd(detail.cost_usd)} total
          {isRun && (
            <>
              {" "}·{" "}
              <Link
                href={`/strategies/new?run=${detail.ref_id}`}
                className="underline-offset-2 hover:underline"
              >
                open run
              </Link>
            </>
          )}
        </p>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>#</TableHead>
            <TableHead>Step</TableHead>
            <TableHead>Tier</TableHead>
            <TableHead>Model</TableHead>
            <TableHead className="text-right">In</TableHead>
            <TableHead className="text-right">Cached</TableHead>
            <TableHead className="text-right">Out</TableHead>
            <TableHead className="text-right">Thinking</TableHead>
            <TableHead className="text-right">Latency</TableHead>
            <TableHead className="text-right">Cost</TableHead>
            <TableHead>At</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {detail.calls.map((c, i) => (
            <TableRow key={c.id}>
              <TableCell className="text-xs text-muted-foreground">{i + 1}</TableCell>
              <TableCell className="font-mono text-xs">
                {c.step ?? "—"}
                {!c.ok && (
                  <Badge variant="destructive" className="ml-2" title={c.error ?? undefined}>
                    failed
                  </Badge>
                )}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">{c.tier ?? "—"}</TableCell>
              <TableCell className="font-mono text-xs">{c.model}</TableCell>
              <TableCell className="text-right text-xs">{fmtTokens(c.prompt_tokens)}</TableCell>
              <TableCell className="text-right text-xs">{fmtTokens(c.cached_tokens)}</TableCell>
              <TableCell className="text-right text-xs">{fmtTokens(c.completion_tokens)}</TableCell>
              <TableCell className="text-right text-xs">{fmtTokens(c.thinking_tokens)}</TableCell>
              <TableCell className="text-right text-xs">{fmtMs(c.latency_ms)}</TableCell>
              <TableCell className="text-right font-mono text-xs">
                {c.ok && c.cost_usd == null ? (
                  <span className="text-destructive">unpriced</span>
                ) : (
                  fmtUsd(c.cost_usd)
                )}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {new Date(c.created_at).toLocaleTimeString()}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {detail.calls.some((c) => c.error) && (
        <div className="space-y-1 text-xs text-muted-foreground">
          {detail.calls
            .filter((c) => c.error)
            .map((c) => (
              <p key={c.id} className="font-mono">
                {c.step ?? "call"}: {c.error}
              </p>
            ))}
        </div>
      )}
    </div>
  );
}
