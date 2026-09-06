"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
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

import { TestFlightCard } from "../new/cards";
import { TestArtifact } from "../model";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Strategy = Record<string, any>;

export function StrategyDetail({ strategy }: { strategy: Strategy }) {
  const router = useRouter();
  const [showCode, setShowCode] = useState(false);
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<TestArtifact | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const params: Record<string, { default?: number; description?: string }> =
    strategy.parameters_json ?? {};
  const description = strategy.ai_description || strategy.description || "";

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

  async function evaluate() {
    const res = await fetch(`/api/bff/strategies/${strategy.id}/evaluate`, {
      method: "POST",
    });
    if (res.ok) {
      toast.success(
        "Full evaluation queued — results appear on the leaderboard when done.",
      );
    } else {
      toast.error("Could not queue the evaluation.");
    }
  }

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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex flex-wrap items-center gap-2 text-3xl font-semibold tracking-tight">
            {strategy.strategy_name}
            {strategy.validation_status === "validated" && (
              <Badge variant="secondary">validated</Badge>
            )}
            {strategy.validation_status === "failed" && (
              <Badge variant="destructive">draft — failed checks</Badge>
            )}
          </h1>
          {description && (
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
              {description}
            </p>
          )}
        </div>
        {strategy.is_owner && (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" asChild>
              <Link href={`/strategies/new?seed=${strategy.id}`}>Evolve</Link>
            </Button>
            <Button variant="outline" onClick={evaluate}>
              Run full evaluation
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
          </div>
        )}
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

      <div className="space-y-3">
        <Button onClick={runTest} disabled={testing || !strategy.code}>
          {testing ? "Running test flight…" : "Run a test flight"}
        </Button>
        {testError && <p className="text-sm text-red-600">{testError}</p>}
        {test && <TestFlightCard test={test} />}
      </div>
    </div>
  );
}
