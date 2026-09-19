"use client";

/**
 * Ask questions about a strategy's observed behavior. One thread per
 * subject: a designer build (generation run) or a finished simulation. The
 * same panel serves both; only `onUseAsFeedback` differs — the designer
 * passes it so a proposed change can be handed straight to its refine step.
 */
import { FormEvent, useEffect, useRef, useState } from "react";

import { Markdown } from "@/components/markdown";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export type QaSubjectType = "generation_run" | "simulation";

export type QaMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  on_topic: boolean | null;
  suggested_change: { summary: string; refine_feedback: string } | null;
  created_at: string;
};

type ThreadResponse = {
  thread_id: string | null;
  messages: QaMessage[];
  can_refine: boolean;
};

type AskResponse = {
  thread_id: string;
  user: QaMessage;
  assistant: QaMessage;
  can_refine: boolean;
};

const SUGGESTIONS: Record<QaSubjectType, string[]> = {
  generation_run: [
    "Why did the worst path end where it did?",
    "Which rule never fired in these test runs, and why?",
    "What would need to change for the strategy to reach its next phase sooner?",
  ],
  simulation: [
    "What drove the chance of ruin in this run?",
    "Why does the median path look the way it does after year 10?",
    "What change to the strategy would most improve the worst outcomes?",
  ],
};

export function QaPanel({
  subjectType,
  subjectId,
  onUseAsFeedback,
  title = "Ask about this strategy",
}: {
  subjectType: QaSubjectType;
  subjectId: string;
  /** Present when a proposed change can be applied (designer review step). */
  onUseAsFeedback?: (feedback: string) => void;
  title?: string;
}) {
  const [messages, setMessages] = useState<QaMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLLIElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    const qs = new URLSearchParams({ subject_type: subjectType, subject_id: subjectId });
    fetch(`/api/bff/qa/thread?${qs}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(await errorDetail(res));
        return (await res.json()) as ThreadResponse;
      })
      .then((thread) => {
        if (cancelled) return;
        setMessages(thread.messages);
        setError(null);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [subjectType, subjectId]);

  useEffect(() => {
    if (messages.length) endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages.length]);

  async function ask(text: string) {
    const trimmed = text.trim();
    if (!trimmed || pending) return;
    setPending(true);
    setError(null);
    setQuestion("");
    try {
      const res = await fetch("/api/bff/qa/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject_type: subjectType,
          subject_id: subjectId,
          question: trimmed,
        }),
      });
      if (!res.ok) throw new Error(await errorDetail(res));
      const body = (await res.json()) as AskResponse;
      setMessages((prev) => [...prev, body.user, body.assistant]);
    } catch (e) {
      setError((e as Error).message);
      setQuestion(trimmed);
    } finally {
      setPending(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void ask(question);
  }

  // The designer passes onUseAsFeedback only while paused at review — live
  // client state, unlike the server's can_refine snapshot.
  const showRefine = Boolean(onUseAsFeedback);

  return (
    <Card data-testid="qa-panel">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{title}</CardTitle>
        <p className="text-sm text-muted-foreground">
          Questions about how it behaved, why, and what would need to change.
          Answers are grounded in this strategy&apos;s code and these results.
        </p>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {messages.length === 0 && loaded && !error && (
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS[subjectType].map((s) => (
              <button
                key={s}
                type="button"
                disabled={pending}
                onClick={() => void ask(s)}
                className="rounded-full border px-3 py-1 text-xs hover:bg-muted disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.length > 0 && (
          <ol className="space-y-3">
            {messages.map((m) => (
              <li
                key={m.id}
                data-role={m.role}
                className={
                  m.role === "user"
                    ? "ml-8 rounded-lg bg-muted px-3 py-2"
                    : "mr-4 rounded-lg border px-3 py-2"
                }
              >
                {m.role === "user" ? (
                  <p className="whitespace-pre-wrap">{m.content}</p>
                ) : m.on_topic === false ? (
                  <p className="text-muted-foreground">{m.content}</p>
                ) : (
                  <Markdown>{m.content}</Markdown>
                )}
                {m.role === "assistant" && m.suggested_change && (
                  <div className="mt-2 flex flex-wrap items-center gap-2 border-t pt-2">
                    <span className="text-xs text-muted-foreground">
                      Suggested change: {m.suggested_change.summary}
                    </span>
                    {showRefine && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          onUseAsFeedback?.(m.suggested_change!.refine_feedback)
                        }
                      >
                        Use as refine feedback
                      </Button>
                    )}
                  </div>
                )}
              </li>
            ))}
            {pending && (
              <li className="mr-4 rounded-lg border px-3 py-2 text-muted-foreground">
                Thinking…
              </li>
            )}
            <li ref={endRef} aria-hidden className="h-0 list-none" />
          </ol>
        )}
        {messages.length === 0 && pending && (
          <p className="text-muted-foreground">Thinking…</p>
        )}
        {error && <p className="text-destructive">{error}</p>}
        <form onSubmit={submit} className="flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={pending}
            placeholder="e.g. why do we never reach the transition phase?"
            aria-label="Your question"
            className="flex-1 rounded-md border bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
          />
          <Button type="submit" disabled={pending || !question.trim()}>
            Ask
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

async function errorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // fall through
  }
  return res.status === 401 ? "Sign in to ask questions" : `Request failed (${res.status})`;
}
