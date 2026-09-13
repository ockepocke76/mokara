"use client";

/**
 * The strategy designer: a build log that becomes a document
 * (W5_DESIGNER_UX.md). Entry form -> run -> SSE-tailed stage cards ->
 * clarify/review interrupts -> saved strategy.
 *
 * State is authoritative on the server (persisted build-log events); this
 * component rehydrates from GET /generate/{run} and then tails the SSE
 * stream, feeding one reducer. Reload-safe by construction.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { RunEvent, RunModel, STAGES, STAGE_LABELS, buildModel } from "../model";
import {
  BehaviorCard,
  BlueprintCard,
  ChecksCard,
  CodeCard,
  ExamplesCard,
  SpecCard,
  TestFlightCard,
} from "./cards";
import { FlowDiagram } from "./flow-diagram";

const STARTERS: { label: string; text: string }[] = [
  {
    label: "Trinity-style 4% rule",
    text: "I want a simple retirement withdrawal strategy based on the Trinity Study: withdraw 4% of the initial portfolio in year one, then adjust that amount for inflation every year, funded by selling assets.",
  },
  {
    label: "Buy, Borrow, Die",
    text: "I want a tax-efficient strategy that borrows against my portfolio instead of selling. Withdraw about 3% a year funded by new loans, keep loan-to-value under 30%, and start deleveraging by selling if LTV passes 45%.",
  },
  {
    label: "Crash-aware withdrawals",
    text: "Withdraw 4% of the initial portfolio adjusted for inflation, but after any year the market falls more than 15%, cut the withdrawal by a quarter until the portfolio recovers its previous peak.",
  },
];

type SeedStrategy = { id: number; strategy_name: string } | null;

export function Designer({
  seedStrategy,
  initialRunId,
}: {
  seedStrategy: SeedStrategy;
  initialRunId: string | null;
}) {
  const router = useRouter();
  const [runId, setRunId] = useState<string | null>(initialRunId);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [startError, setStartError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [request, setRequest] = useState("");
  const [name, setName] = useState("");

  const model: RunModel = useMemo(() => buildModel(events), [events]);
  const abortRef = useRef<AbortController | null>(null);

  const appendEvents = useCallback((incoming: RunEvent[]) => {
    if (!incoming.length) return;
    setEvents((prev) => {
      const seen = new Set(prev.map((e) => e.seq));
      const fresh = incoming.filter((e) => !seen.has(e.seq));
      return fresh.length ? [...prev, ...fresh] : prev;
    });
  }, []);

  const tail = useCallback(
    async (id: string, after: number) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      let cursor = after;
      while (!controller.signal.aborted) {
        try {
          const res = await fetch(
            `/api/bff/strategies/generate/${id}/events?after=${cursor}`,
            { signal: controller.signal },
          );
          if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          let terminal = false;
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            // SSE framing: normalize CRLF, split on blank lines, and join
            // multi-line data fields per the spec.
            buffer = (buffer + decoder.decode(value, { stream: true })).replace(
              /\r\n/g,
              "\n",
            );
            const chunks = buffer.split("\n\n");
            buffer = chunks.pop() ?? "";
            for (const chunk of chunks) {
              const data = chunk
                .split("\n")
                .filter((l) => l.startsWith("data:"))
                .map((l) => l.replace(/^data: ?/, ""))
                .join("\n");
              if (!data) continue;
              const event: RunEvent = JSON.parse(data);
              cursor = Math.max(cursor, event.seq);
              appendEvents([event]);
              if (
                ["run_completed", "run_failed", "run_discarded"].includes(
                  event.type,
                )
              ) {
                terminal = true;
              }
            }
            if (terminal) break;
          }
          if (terminal) return;
        } catch {
          if (controller.signal.aborted) return;
        }
        await new Promise((r) => setTimeout(r, 1500));
      }
    },
    [appendEvents],
  );

  // Rehydrate an existing run (reload / came back later), then tail live.
  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    (async () => {
      const res = await fetch(`/api/bff/strategies/generate/${runId}`);
      if (!res.ok) {
        setStartError("Could not load this generation run.");
        return;
      }
      const body = await res.json();
      if (cancelled) return;
      const existing: RunEvent[] = body.events ?? [];
      appendEvents(existing);
      const terminal = existing.some((e) =>
        ["run_completed", "run_failed", "run_discarded"].includes(e.type),
      );
      const last = existing.length ? existing[existing.length - 1].seq : 0;
      if (!terminal) void tail(runId, last);
    })();
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  async function start() {
    setBusy(true);
    setStartError(null);
    try {
      const res = await fetch("/api/bff/strategies/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request,
          strategy_name: name || undefined,
          seed_strategy_id: seedStrategy?.id,
        }),
      });
      const body = await res.json();
      if (!res.ok) {
        setStartError(
          typeof body.detail === "string"
            ? body.detail
            : "Could not start the generation run.",
        );
        return;
      }
      setEvents([]);
      setRunId(body.run_id);
      router.replace(`/strategies/new?run=${body.run_id}`, { scroll: false });
    } finally {
      setBusy(false);
    }
  }

  async function resume(payload: Record<string, unknown>) {
    if (!runId) return;
    setBusy(true);
    try {
      await fetch(`/api/bff/strategies/generate/${runId}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } finally {
      setBusy(false);
    }
  }

  if (!runId) {
    return (
      <EntryForm
        seedStrategy={seedStrategy}
        request={request}
        setRequest={setRequest}
        name={name}
        setName={setName}
        onStart={start}
        busy={busy}
        error={startError}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6 lg:flex-row">
      <StageRail model={model} />
      <div className="min-w-0 flex-1 space-y-4">
        {seedStrategy && (
          <Badge variant="outline">Based on: {seedStrategy.strategy_name}</Badge>
        )}
        <BuildLog model={model} busy={busy} onResume={resume} />
      </div>
    </div>
  );
}

function EntryForm({
  seedStrategy,
  request,
  setRequest,
  name,
  setName,
  onStart,
  busy,
  error,
}: {
  seedStrategy: SeedStrategy;
  request: string;
  setRequest: (v: string) => void;
  name: string;
  setName: (v: string) => void;
  onStart: () => void;
  busy: boolean;
  error: string | null;
}) {
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {seedStrategy ? (
        <p className="text-sm text-muted-foreground">
          Evolving <span className="font-medium">{seedStrategy.strategy_name}</span>{" "}
          — describe what should change.
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">
          Describe the strategy in your own words. Good prompts mention: your
          goal (withdraw or build wealth), when to sell or borrow, and what to
          do in a crash.
        </p>
      )}
      <div className="space-y-2">
        <Label htmlFor="request">
          {seedStrategy ? "What should change?" : "What should the strategy do?"}
        </Label>
        <textarea
          id="request"
          value={request}
          onChange={(e) => setRequest(e.target.value)}
          rows={6}
          className="w-full rounded-md border bg-transparent p-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          placeholder="e.g. Withdraw 4% a year adjusted for inflation, but cut spending after a crash…"
        />
      </div>
      {!seedStrategy && (
        <div className="flex flex-wrap gap-2">
          {STARTERS.map((s) => (
            <button
              key={s.label}
              type="button"
              onClick={() => setRequest(s.text)}
              className="rounded-full border px-3 py-1 text-xs text-muted-foreground hover:bg-muted"
            >
              {s.label}
            </button>
          ))}
        </div>
      )}
      <div className="space-y-2">
        <Label htmlFor="name">Strategy name (optional — I&apos;ll suggest one)</Label>
        <Input
          id="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Storm Shelter"
        />
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <Button onClick={onStart} disabled={busy || request.trim().length < 10}>
        {busy ? "Starting…" : "Generate — uses 1 AI credit"}
      </Button>
      <FlowDiagram />
    </div>
  );
}

function StageRail({ model }: { model: RunModel }) {
  return (
    <ol className="flex shrink-0 flex-row flex-wrap gap-2 lg:w-48 lg:flex-col">
      {STAGES.map((stage) => {
        const status = model.stages[stage];
        const dot =
          status === "done"
            ? "bg-emerald-500"
            : status === "active"
              ? "animate-pulse bg-blue-500"
              : status === "needs_you"
                ? "bg-amber-500"
                : status === "failed"
                  ? "bg-red-500"
                  : "bg-muted-foreground/30";
        return (
          <li key={stage} className="flex items-center gap-2 text-sm">
            <span className={`h-2.5 w-2.5 rounded-full ${dot}`} />
            <span
              className={
                status === "pending" ? "text-muted-foreground" : "font-medium"
              }
            >
              {STAGE_LABELS[stage]}
              {status === "needs_you" ? " — needs you" : ""}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function BuildLog({
  model,
  busy,
  onResume,
}: {
  model: RunModel;
  busy: boolean;
  onResume: (payload: Record<string, unknown>) => void;
}) {
  const lastAttempt = model.attempts.at(-1);
  const attemptNote = lastAttempt
    ? `Attempt ${lastAttempt.attempt} of ${lastAttempt.max} — fixing: ${lastAttempt.reason}`
    : null;

  return (
    <div className="space-y-4">
      {model.spec && (
        <SpecCard spec={model.spec} strategyName={model.strategyName} />
      )}
      {model.needsInput?.kind === "clarify" && (
        <ClarifyCard
          needsInput={model.needsInput}
          busy={busy}
          onResume={onResume}
        />
      )}
      {model.examples && <ExamplesCard examples={model.examples} />}
      {model.plan && <BlueprintCard plan={model.plan} />}
      {model.code && (
        <CodeCard
          code={model.code}
          description={model.codeDescription}
          isEvolution={model.isEvolution}
        />
      )}
      {(model.checks.length > 0 || attemptNote) && (
        <ChecksCard checks={model.checks} attemptNote={attemptNote} />
      )}
      {model.test && <TestFlightCard test={model.test} />}
      {model.analyze && <BehaviorCard analyze={model.analyze} />}
      {model.needsInput?.kind === "review" && (
        <ReviewCard
          revisionsLeft={model.needsInput.revisions_left}
          busy={busy}
          onResume={onResume}
        />
      )}
      {model.terminal && <TerminalCard model={model} />}
      {!model.terminal && !model.needsInput && (
        <p className="text-sm text-muted-foreground">Working…</p>
      )}
    </div>
  );
}

function ClarifyCard({
  needsInput,
  busy,
  onResume,
}: {
  needsInput: NonNullable<RunModel["needsInput"]>;
  busy: boolean;
  onResume: (payload: Record<string, unknown>) => void;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const questions = needsInput.questions ?? [];
  return (
    <Card className="border-amber-500/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">A couple of questions first</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {questions.map((q) => (
          <div key={q.question} className="space-y-1.5">
            <p className="font-medium">{q.question}</p>
            {q.options?.length ? (
              <div className="flex flex-wrap gap-2">
                {q.options.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() =>
                      setAnswers((a) => ({ ...a, [q.question]: opt }))
                    }
                    className={`rounded-full border px-3 py-1 text-xs ${
                      answers[q.question] === opt
                        ? "border-primary bg-primary text-primary-foreground"
                        : "hover:bg-muted"
                    }`}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            ) : null}
            <Input
              placeholder="Or answer in your own words"
              value={answers[q.question] ?? ""}
              onChange={(e) =>
                setAnswers((a) => ({ ...a, [q.question]: e.target.value }))
              }
            />
          </div>
        ))}
        <div className="flex gap-2">
          <Button
            disabled={busy || questions.some((q) => !answers[q.question])}
            onClick={() => onResume({ kind: "clarify", answers })}
          >
            Continue
          </Button>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => onResume({ kind: "clarify" })}
          >
            Proceed with my assumptions
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ReviewCard({
  revisionsLeft,
  busy,
  onResume,
}: {
  revisionsLeft?: number;
  busy: boolean;
  onResume: (payload: Record<string, unknown>) => void;
}) {
  const [feedback, setFeedback] = useState("");
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  return (
    <Card className="border-amber-500/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Your decision</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">
          It does what the blueprint says. Save it, ask for changes, or discard
          it. The full 8-scenario evaluation is the fair performance test —
          run it after saving.
        </p>
        <div className="flex flex-wrap items-start gap-2">
          <Button disabled={busy} onClick={() => onResume({ kind: "review", action: "save" })}>
            Save strategy
          </Button>
          {!confirmDiscard ? (
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => setConfirmDiscard(true)}
            >
              Discard
            </Button>
          ) : (
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => onResume({ kind: "review", action: "discard" })}
            >
              Really discard?
            </Button>
          )}
        </div>
        <div className="space-y-2">
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            rows={2}
            className="w-full rounded-md border bg-transparent p-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            placeholder="…or describe a change, e.g. “make the crash cut deeper”"
          />
          <Button
            variant="outline"
            disabled={busy || !feedback.trim() || (revisionsLeft ?? 1) < 1}
            onClick={() =>
              onResume({ kind: "review", action: "refine", feedback })
            }
          >
            Request changes
            {revisionsLeft !== undefined
              ? ` (${revisionsLeft} round${revisionsLeft === 1 ? "" : "s"} left)`
              : ""}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function TerminalCard({ model }: { model: RunModel }) {
  const terminal = model.terminal!;
  if (terminal.type === "run_completed") {
    const id = terminal.payload.strategy_id as number;
    return (
      <Card className="border-emerald-500/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            Saved: {String(terminal.payload.strategy_name ?? model.strategyName)}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2 text-sm">
          <Button asChild>
            <Link href={`/strategies/${id}`}>View strategy</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href={`/strategies/${id}?evaluate=1`}>
              Run the full evaluation
            </Link>
          </Button>
          <Button variant="ghost" asChild>
            <Link href="/strategies/new">Design another</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }
  if (terminal.type === "run_failed") {
    const draftId = terminal.payload.draft_id as number | null;
    return (
      <Card className="border-red-500/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            I couldn&apos;t get this working
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p>{String(terminal.payload.summary ?? "")}</p>
          {draftId ? (
            <p className="text-muted-foreground">
              The last draft is kept —{" "}
              <Link href={`/strategies/${draftId}`} className="underline">
                inspect it
              </Link>{" "}
              or try again with a more specific request.
            </p>
          ) : (
            <p className="text-muted-foreground">
              Try again with a more specific request, or start from a template.
            </p>
          )}
          <Button variant="outline" asChild>
            <Link href="/strategies/new">Start over</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Discarded</CardTitle>
      </CardHeader>
      <CardContent className="text-sm">
        <Button variant="outline" asChild>
          <Link href="/strategies/new">Design another</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
