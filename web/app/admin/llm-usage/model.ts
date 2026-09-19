// Shapes returned by /admin/llm-usage/* (api/app/routers/admin_llm_usage.py)
// plus the formatters the three usage pages share.

export type OperationStats = {
  operation: string;
  n: number;
  mean_cost_usd: number | null;
  median_cost_usd: number | null;
  p90_cost_usd: number | null;
  max_cost_usd: number | null;
  total_cost_usd: number | null;
  mean_calls: number;
  mean_prompt_tokens: number;
  mean_cached_tokens: number;
  mean_completion_tokens: number;
  mean_thinking_tokens: number;
  mean_latency_ms: number | null;
  unpriced_calls: number;
  failed_calls: number;
  window_from: string | null;
  window_to: string | null;
};

export type StepStats = {
  step: string;
  tier: string;
  calls: number;
  calls_per_operation: number;
  cost_per_operation_usd: number | null;
  mean_cost_usd: number | null;
  mean_prompt_tokens: number;
  mean_completion_tokens: number;
  mean_thinking_tokens: number;
  mean_latency_ms: number | null;
};

export type Totals = {
  days: number;
  cost_usd: number;
  by_operation: {
    operation: string;
    operations: number;
    calls: number;
    cost_usd: number | null;
    unpriced_calls: number;
  }[];
  by_day: { day: string; operations: number; cost_usd: number | null }[];
  all_time_cost_usd: number;
  all_time_calls: number;
};

export type Price = {
  input: number;
  output: number;
  cached: number;
  effective_from: string;
};

export type Summary = {
  window: number;
  operations: OperationStats[];
  totals: Totals;
  prices: Record<string, Price | null>;
};

export type UserTotals = {
  user_id: number | null;
  email: string | null;
  name: string | null;
  tier: string | null;
  operations: number;
  cost_usd: number | null;
  strategy_create: number;
  strategy_evolve: number;
  strategy_qa: number;
  report_analysis: number;
  other: number;
  last_activity: string | null;
};

export type OperationRow = {
  operation: string;
  ref_id: string;
  user_id?: number | null;
  email?: string | null;
  calls: number;
  failed_calls: number;
  unpriced_calls: number;
  cost_usd: number | null;
  prompt_tokens: number;
  cached_tokens: number;
  completion_tokens: number;
  thinking_tokens: number;
  latency_ms: number | null;
  started_at: string;
  finished_at: string;
};

export type CallRow = {
  id: number;
  created_at: string;
  user_id: number | null;
  step: string | null;
  tier: string | null;
  model: string;
  prompt_tokens: number;
  cached_tokens: number;
  completion_tokens: number;
  thinking_tokens: number;
  cost_usd: number | null;
  latency_ms: number | null;
  ok: boolean;
  error: string | null;
};

export const OPERATION_LABELS: Record<string, string> = {
  strategy_create: "Strategy creation",
  strategy_evolve: "Strategy evolution",
  strategy_qa: "Strategy Q&A",
  report_analysis: "Report analysis",
  unknown: "Unscoped calls",
};

export function operationLabel(op: string): string {
  return OPERATION_LABELS[op] ?? op;
}

// Costs per operation are cents, not dollars — keep enough precision to
// see them, but don't drown totals in decimals.
export function fmtUsd(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v === 0) return "$0";
  if (v < 0.01) return `$${v.toFixed(4)}`;
  if (v < 1) return `$${v.toFixed(3)}`;
  return `$${v.toFixed(2)}`;
}

export function fmtTokens(v: number | null | undefined): string {
  if (v == null) return "—";
  const n = Math.round(v);
  return n >= 10_000 ? `${(n / 1000).toFixed(1)}k` : n.toLocaleString();
}

export function fmtMs(v: number | null | undefined): string {
  if (v == null) return "—";
  return v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${Math.round(v)}ms`;
}

export function fmtWhen(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString() : "—";
}
