"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type ActionState = { state: "idle" | "busy" | "done" | "error"; note?: string };

export function SystemActions() {
  const [migrations, setMigrations] = useState<ActionState>({ state: "idle" });
  const [evals, setEvals] = useState<ActionState>({ state: "idle" });
  const [reset, setReset] = useState<ActionState>({ state: "idle" });
  const [password, setPassword] = useState("");
  const [confirmText, setConfirmText] = useState("");

  async function runMigrations() {
    setMigrations({ state: "busy" });
    const res = await fetch("/api/bff/admin/migrations/run", { method: "POST" });
    setMigrations(res.ok ? { state: "done", note: "Migrations up to date." } : { state: "error", note: "Failed — see API logs." });
  }

  async function runEvaluations() {
    setEvals({ state: "busy" });
    const res = await fetch("/api/bff/admin/evaluations/run", { method: "POST" });
    if (res.ok) {
      const body = await res.json();
      setEvals({ state: "done", note: `Queued ${body.queued} evaluation jobs (worker must be running).` });
    } else {
      setEvals({ state: "error", note: "Failed to queue evaluations." });
    }
  }

  async function systemReset(e: React.FormEvent) {
    e.preventDefault();
    setReset({ state: "busy" });
    const res = await fetch("/api/bff/admin/system-reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        admin_password: password,
        confirmation_text: confirmText,
      }),
    });
    if (res.ok) {
      setReset({ state: "done", note: "Database wiped. Run migrations to rebuild the schema." });
      setPassword("");
      setConfirmText("");
    } else {
      const body = await res.json().catch(() => ({}));
      setReset({ state: "error", note: body.detail ?? "Reset refused." });
    }
  }

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Database migrations</CardTitle>
          <CardDescription>
            Apply any pending schema migrations (idempotent).
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center gap-3">
          <Button onClick={runMigrations} disabled={migrations.state === "busy"}>
            {migrations.state === "busy" ? "Running…" : "Run migrations"}
          </Button>
          {migrations.note && (
            <p className="text-sm text-muted-foreground">{migrations.note}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Leaderboard evaluations</CardTitle>
          <CardDescription>
            Re-evaluate all built-in and community strategies (queues one
            background job per strategy).
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center gap-3">
          <Button onClick={runEvaluations} disabled={evals.state === "busy"}>
            {evals.state === "busy" ? "Queuing…" : "Re-run evaluations"}
          </Button>
          {evals.note && (
            <p className="text-sm text-muted-foreground">{evals.note}</p>
          )}
        </CardContent>
      </Card>

      <Card className="border-destructive/50">
        <CardHeader>
          <CardTitle className="text-destructive">Danger zone</CardTitle>
          <CardDescription>
            Wipes the entire database. Requires the admin password and typing
            DELETE-EVERYTHING exactly.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={systemReset} className="flex flex-col gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="reset-pw">Admin password</Label>
              <Input
                id="reset-pw"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="reset-confirm">
                Type <span className="font-mono">DELETE-EVERYTHING</span>
              </Label>
              <Input
                id="reset-confirm"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                required
              />
            </div>
            {reset.note && (
              <p
                className={`text-sm ${reset.state === "error" ? "text-destructive" : "text-muted-foreground"}`}
              >
                {reset.note}
              </p>
            )}
            <Button
              type="submit"
              variant="destructive"
              disabled={reset.state === "busy"}
              className="self-start"
            >
              {reset.state === "busy" ? "Wiping…" : "Wipe database"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
