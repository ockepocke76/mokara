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
  const [reset, setReset] = useState<ActionState>({ state: "idle" });
  const [password, setPassword] = useState("");
  const [confirmText, setConfirmText] = useState("");

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
    <div className="flex flex-col gap-6">
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
