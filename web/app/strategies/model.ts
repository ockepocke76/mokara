/**
 * Client model for a strategy-generation run: a fold over the persisted
 * build-log events. The server's event log is authoritative; reload
 * rehydration and live SSE tailing both feed the same reducer.
 */

export type RunEvent = {
  seq: number;
  type: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload: any;
};

export { STAGES, STAGE_LABELS, type StageKey } from "@/lib/stage-labels";
import { STAGES, type StageKey } from "@/lib/stage-labels";

export type StageStatus = "pending" | "active" | "done" | "needs_you" | "failed";

/** Which rail stage an interrupt kind belongs to (server emits kind on both
 * needs_input and input_received). */
const STAGE_FOR_KIND = { clarify: "understanding", review: "decision" } as const;

export type CheckItem = {
  check: string;
  passed: boolean;
  message?: string;
  rule_verdicts?: { rule: string; implemented: boolean; note?: string }[];
  issues?: string[];
};

export type AttemptNote = {
  stage: string;
  attempt: number;
  max: number;
  reason: string;
  afterSeq: number;
};

export type Spec = {
  summary?: string;
  category?: string;
  mechanics?: string[];
  assumptions?: string[];
  constraints?: string[];
  proposed_parameters?: { name: string; default?: number; description?: string }[];
  // Evolve runs: the change spec
  changes?: string[];
  change_scope?: "parameter_only" | "behavioral" | "structural" | string;
};

export type TestPath = {
  label: string;
  years: number[];
  net_worth: (number | null)[];
  // Optional yearly series (older runs' persisted events carry only net_worth)
  asset_value?: (number | null)[];
  debt?: (number | null)[];
  cash?: (number | null)[];
  contributed?: (number | null)[];
  withdrawn?: (number | null)[];
  // Debt-funded flows (e.g. Buy Borrow Die): 'withdrawn' is zero there, so
  // these carry the real annual cash flow.
  borrowed?: (number | null)[];
  sold?: (number | null)[];
  is_backtest?: boolean;
};

export type TestArtifact = {
  summary_stats: Record<string, number | string | null>;
  paths?: TestPath[];
  baseline?: { name: string; summary_stats: Record<string, number | null> } | null;
  num_paths?: number;
  num_years?: number;
};

export type AnalyzeArtifact = {
  conforms_to_spec?: boolean;
  mismatches?: string[];
  typical_year?: string;
  worst_path_story?: string;
  explanation?: string;
  notes?: string;
};

export type NeedsInput = {
  kind: "clarify" | "review";
  questions?: { question: string; options?: string[] }[];
  assumptions?: string[];
  revisions_left?: number;
};

export type RunModel = {
  stages: Record<StageKey, StageStatus>;
  strategyName?: string;
  seedStrategy?: { id: number; name?: string } | null;
  spec?: Spec;
  examples?: { name: string; source: string; score?: number | null }[];
  plan?: { rules?: string[]; parameters?: { name: string; default?: number; description?: string }[] };
  code?: string;
  codeDescription?: string;
  codeDiff?: string;
  className?: string;
  isEvolution?: boolean;
  checks: CheckItem[];
  test?: TestArtifact;
  analyze?: AnalyzeArtifact;
  attempts: AttemptNote[];
  needsInput?: NeedsInput | null;
  terminal?: { type: string; payload: Record<string, unknown> } | null;
  lastSeq: number;
};

export function buildModel(events: RunEvent[]): RunModel {
  const model: RunModel = {
    stages: Object.fromEntries(STAGES.map((s) => [s, "pending"])) as Record<
      StageKey,
      StageStatus
    >,
    checks: [],
    attempts: [],
    lastSeq: 0,
    needsInput: null,
    terminal: null,
  };

  for (const event of events) {
    model.lastSeq = Math.max(model.lastSeq, event.seq);
    const p = event.payload ?? {};
    switch (event.type) {
      case "run_started":
        model.strategyName = p.strategy_name || model.strategyName;
        model.seedStrategy = p.seed_strategy ?? null;
        break;
      case "stage_started": {
        const stage = p.stage as StageKey;
        if (model.stages[stage] !== undefined) model.stages[stage] = "active";
        break;
      }
      case "stage_progress": {
        if (p.stage === "checks" && p.check) {
          model.checks = [
            ...model.checks.filter((c) => c.check !== p.check),
            p as CheckItem,
          ];
        }
        break;
      }
      case "stage_completed": {
        const stage = p.stage as StageKey;
        if (model.stages[stage] !== undefined) model.stages[stage] = "done";
        const artifact = p.artifact ?? {};
        if (stage === "understanding") {
          model.spec = artifact.spec;
          model.strategyName = artifact.strategy_name || model.strategyName;
        } else if (stage === "examples") {
          model.examples = artifact.examples ?? [];
        } else if (stage === "blueprint") {
          model.plan = artifact.plan;
        } else if (stage === "code") {
          model.code = artifact.code;
          model.codeDescription = artifact.description;
          model.codeDiff = artifact.diff;
          model.className = artifact.class_name;
          model.isEvolution = artifact.is_evolution;
          // A fresh code round resets everything downstream of it.
          model.checks = [];
          model.test = undefined;
          model.analyze = undefined;
          for (const s of ["checks", "test_flight", "behavior", "decision"] as StageKey[]) {
            model.stages[s] = "pending";
          }
        } else if (stage === "test_flight") {
          model.test = artifact as TestArtifact;
        } else if (stage === "behavior") {
          model.analyze = artifact.analyze as AnalyzeArtifact;
        }
        break;
      }
      case "attempt_started":
        model.attempts.push({
          stage: p.stage,
          attempt: p.attempt,
          max: p.max,
          reason: p.reason,
          afterSeq: event.seq,
        });
        break;
      case "needs_input": {
        model.needsInput = p as NeedsInput;
        const stage = STAGE_FOR_KIND[p.kind as keyof typeof STAGE_FOR_KIND];
        if (stage) model.stages[stage] = "needs_you";
        break;
      }
      case "input_received": {
        model.needsInput = null;
        const stage = STAGE_FOR_KIND[p.kind as keyof typeof STAGE_FOR_KIND];
        if (stage && model.stages[stage] === "needs_you")
          model.stages[stage] = "active";
        break;
      }
      case "run_completed":
        model.terminal = { type: event.type, payload: p };
        model.stages.decision = "done";
        model.needsInput = null;
        break;
      case "run_failed":
      case "run_discarded":
        model.terminal = { type: event.type, payload: p };
        model.needsInput = null;
        if (event.type === "run_failed") {
          for (const s of STAGES) {
            if (model.stages[s] === "active" || model.stages[s] === "needs_you")
              model.stages[s] = "failed";
          }
        }
        break;
    }
  }
  return model;
}

export const fmtCompact = new Intl.NumberFormat("en", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export function fmtPercent(value: unknown): string {
  const n = typeof value === "number" ? value : NaN;
  return Number.isFinite(n) ? `${Math.round(n * 100)}%` : "—";
}
