"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MermaidChart } from "@/components/mermaid-chart";
import { Markdown } from "@/components/markdown";

import { TestFlightCard } from "../new/cards";
import { TestArtifact } from "../model";
import { EvaluationTab } from "./evaluation-tab";
import { FamilyTree } from "./family-tree";
import { HistoryTab } from "./history-tab";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Strategy = Record<string, any>;

export function StrategyDetail({
  strategy,
  autoEvaluate = false,
  viewerName,
}: {
  strategy: Strategy;
  autoEvaluate?: boolean;
  viewerName?: string | null;
}) {
  const router = useRouter();
  const [tab, setTab] = useState(autoEvaluate ? "evaluation" : "overview");

  async function remove() {
    const res = await fetch(`/api/bff/strategies/${strategy.id}`, {
      method: "DELETE",
    });
    if (res.ok) {
      router.push("/strategies");
      router.refresh();
    } else {
      toast.error("Could not delete the strategy.");
    }
  }

  const description = strategy.ai_description || strategy.description || "";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex flex-wrap items-center gap-2 text-3xl font-semibold tracking-tight">
            {strategy.strategy_name}
            {strategy.is_builtin && <Badge>built-in</Badge>}
            {strategy.validation_status === "validated" && (
              <Badge variant="secondary">validated</Badge>
            )}
            {strategy.validation_status === "failed" && (
              <Badge variant="destructive">draft — failed checks</Badge>
            )}
            {strategy.is_published_to_leaderboard && (
              <Badge variant="outline">on the leaderboard</Badge>
            )}
          </h1>
          <UsageBadges strategy={strategy} />
        </div>
        <div className="flex flex-wrap gap-2">
          {strategy.is_owner ? (
            <>
              <Button variant="outline" asChild>
                <Link href={`/strategies/new?seed=${strategy.id}`}>Evolve</Link>
              </Button>
              <Dialog>
                <DialogTrigger asChild>
                  <Button variant="ghost">Delete</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Delete {strategy.strategy_name}?</DialogTitle>
                    <DialogDescription>
                      The strategy is removed from your list. Simulations that
                      used it keep their results.
                    </DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <Button variant="destructive" onClick={remove}>
                      Delete
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </>
          ) : (
            <CloneButton strategy={strategy} />
          )}
        </div>
      </div>

      {strategy.validation_status === "failed" && strategy.validation_error && (
        <Card className="border-red-500/50">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Why the checks failed</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
              {strategy.validation_error}
            </pre>
          </CardContent>
        </Card>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="evaluation">Evaluation</TabsTrigger>
          <TabsTrigger value="test">Test</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <OverviewTab strategy={strategy} description={description} viewerName={viewerName} />
        </TabsContent>

        <TabsContent value="evaluation" className="mt-4">
          <EvaluationTab
            strategyId={strategy.id}
            isOwner={Boolean(strategy.is_owner)}
            hasCode={Boolean(strategy.code)}
            autoStart={autoEvaluate}
          />
        </TabsContent>

        <TabsContent value="test" className="mt-4">
          <TestTab strategy={strategy} />
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          <HistoryTab strategyId={strategy.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function UsageBadges({ strategy }: { strategy: Strategy }) {
  const parts: string[] = [];
  if (strategy.usage_clone_count > 0)
    parts.push(`🔗 ${strategy.usage_clone_count} clone${strategy.usage_clone_count === 1 ? "" : "s"}`);
  if (strategy.usage_fork_count > 0)
    parts.push(`🔱 ${strategy.usage_fork_count} fork${strategy.usage_fork_count === 1 ? "" : "s"}`);
  if (parts.length === 0) return null;
  return (
    <p className="mt-1 text-sm text-muted-foreground">{parts.join(" · ")}</p>
  );
}

function CloneButton({ strategy }: { strategy: Strategy }) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");

  async function clone() {
    setState("busy");
    const res = await fetch(`/api/bff/strategies/${strategy.id}/clone`, {
      method: "POST",
    });
    const body = await res.json();
    if (res.ok) {
      setState("done");
      if (body.cloned) {
        toast.success("Cloned to your library.");
      } else {
        toast.info("Already in your library.");
      }
      if (body.strategy_id) {
        router.push(`/strategies/${body.strategy_id}`);
      } else {
        router.refresh();
      }
    } else {
      setState("idle");
      toast.error(body.detail || "Could not clone the strategy.");
    }
  }

  return (
    <Button onClick={() => void clone()} disabled={state !== "idle"}>
      {state === "busy"
        ? "Cloning…"
        : state === "done"
          ? "Cloned ✓"
          : "Clone to my library"}
    </Button>
  );
}

function OverviewTab({
  strategy,
  description,
  viewerName,
}: {
  strategy: Strategy;
  description: string;
  viewerName?: string | null;
}) {
  const [showCode, setShowCode] = useState(false);
  const [mermaid, setMermaid] = useState<string | null>(null);

  const params: Record<string, { default?: number; description?: string }> =
    strategy.parameters_json ?? {};

  useEffect(() => {
    if (!strategy.is_builtin) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(
          `/api/bff/strategies/${strategy.id}/flowchart?theme=light`,
        );
        if (!res.ok) return;
        const body = await res.json();
        if (!cancelled && body.mermaid) setMermaid(body.mermaid);
      } catch {
        // No flowchart — the section just doesn't render.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [strategy.id, strategy.is_builtin]);

  return (
    <div className="space-y-6">
      {description && (
        <div className="max-w-2xl text-sm text-muted-foreground">
          <Markdown>{description}</Markdown>
        </div>
      )}

      {strategy.is_owner && !strategy.is_builtin && (
        <PublishCard strategy={strategy} viewerName={viewerName} />
      )}

      {Object.keys(params).length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Parameters</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Default</TableHead>
                  <TableHead>Description</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(params).map(([name, conf]) => (
                  <TableRow key={name}>
                    <TableCell className="font-mono text-xs">{name}</TableCell>
                    <TableCell>{String(conf?.default ?? "—")}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {conf?.description ?? ""}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {strategy.code && (
        <div>
          <button
            type="button"
            onClick={() => setShowCode((v) => !v)}
            className="text-xs text-muted-foreground underline underline-offset-2"
          >
            {showCode
              ? "Hide the Python"
              : `View the Python — ${strategy.code.split("\n").length} lines`}
          </button>
          {showCode && (
            <pre className="mt-2 max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs leading-5">
              <code>{strategy.code}</code>
            </pre>
          )}
        </div>
      )}

      {mermaid && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Decision flowchart</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-3 text-sm text-muted-foreground">
              How the strategy makes its annual decisions:
            </p>
            <MermaidChart code={mermaid} />
          </CardContent>
        </Card>
      )}

      <FamilyTree strategyId={strategy.id} />
    </div>
  );
}

function PublishCard({
  strategy,
  viewerName,
}: {
  strategy: Strategy;
  viewerName?: string | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const published = Boolean(strategy.is_published_to_leaderboard);

  async function setPublished(next: boolean) {
    setBusy(true);
    try {
      const res = await fetch(
        `/api/bff/strategies/${strategy.id}/${next ? "publish" : "unpublish"}`,
        { method: "POST" },
      );
      const body = await res.json();
      if (res.ok) {
        toast.success(
          next ? "Published to the leaderboard! 🏆" : "Removed from the leaderboard.",
        );
        setConfirmOpen(false);
        router.refresh();
      } else {
        toast.error(body.detail || "Could not change the publish status.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
        <div className="text-sm">
          <p className="font-medium">
            {published ? "On the public leaderboard" : "Private"}
          </p>
          <p className="text-muted-foreground">
            {published
              ? "Anyone can see this strategy's name, score, and author on the leaderboard."
              : "Publish to compete on the public leaderboard — requires a full evaluation."}
          </p>
        </div>
        {published ? (
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => void setPublished(false)}
          >
            {busy ? "Working…" : "Unpublish"}
          </Button>
        ) : (
          <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
            <DialogTrigger asChild>
              <Button variant="secondary">Publish…</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Publish to the leaderboard?</DialogTitle>
                <DialogDescription>
                  “{strategy.strategy_name}” will appear on the public
                  leaderboard with its excellence score
                  {viewerName ? (
                    <>
                      {" "}
                      under your username <b>{viewerName}</b> (changeable in
                      Settings)
                    </>
                  ) : (
                    " under your username (set one in Settings first)"
                  )}
                  .
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button disabled={busy} onClick={() => void setPublished(true)}>
                  {busy ? "Publishing…" : "Yes, publish"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </CardContent>
    </Card>
  );
}

function TestTab({ strategy }: { strategy: Strategy }) {
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<TestArtifact | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  if (!strategy.is_owner) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Test flights execute the strategy&apos;s code, so only the owner can run
        one — clone it to your library first.
      </p>
    );
  }

  async function runTest() {
    setTesting(true);
    setTestError(null);
    try {
      const res = await fetch(`/api/bff/strategies/${strategy.id}/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const body = await res.json();
      if (!res.ok || !body.success) {
        setTestError(body.error || body.detail || "Test failed");
        return;
      }
      setTest(body as TestArtifact);
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        A quick smoke test — a handful of simulated paths plus the historical
        backtest. Results are not saved and don&apos;t affect the leaderboard;
        for reliable numbers, run a full evaluation.
      </p>
      <Button onClick={runTest} disabled={testing || !strategy.code}>
        {testing ? "Running test flight…" : "Run a test flight"}
      </Button>
      {testError && <p className="text-sm text-red-600">{testError}</p>}
      {test && <TestFlightCard test={test} />}
    </div>
  );
}
