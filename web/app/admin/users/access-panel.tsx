"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";

export type BetaCapacity = {
  max_beta_users: number;
  current_allowed: number;
};

export type LoginRequest = {
  id: number;
  email: string;
  name: string | null;
  first_attempt_at: string | null;
  last_attempt_at: string | null;
  attempt_count: number;
  notes: string | null;
};

export function AccessPanel({
  betaCapacity,
  loginRequests,
}: {
  betaCapacity: BetaCapacity;
  loginRequests: LoginRequest[];
}) {
  const router = useRouter();
  const [maxBeta, setMaxBeta] = useState(String(betaCapacity.max_beta_users));
  const [bulkEmails, setBulkEmails] = useState("");
  const [bulkResult, setBulkResult] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const pct =
    betaCapacity.max_beta_users > 0
      ? Math.min(
          (betaCapacity.current_allowed / betaCapacity.max_beta_users) * 100,
          100,
        )
      : 100;

  async function saveMaxBeta(e: React.FormEvent) {
    e.preventDefault();
    const value = Number(maxBeta);
    if (!Number.isFinite(value) || value < 0) return;
    setBusy("beta");
    await fetch("/api/bff/admin/system-settings/max-beta-users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_beta_users: value }),
    });
    setBusy(null);
    router.refresh();
  }

  async function approveRequest(email: string) {
    setBusy(`approve-${email}`);
    await fetch(
      `/api/bff/admin/login-requests/${encodeURIComponent(email)}/approve`,
      { method: "POST" },
    );
    setBusy(null);
    router.refresh();
  }

  async function dismissRequest(email: string) {
    setBusy(`dismiss-${email}`);
    await fetch(`/api/bff/admin/login-requests/${encodeURIComponent(email)}`, {
      method: "DELETE",
    });
    setBusy(null);
    router.refresh();
  }

  async function submitBulkImport(e: React.FormEvent) {
    e.preventDefault();
    const emails = bulkEmails
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (emails.length === 0) return;
    setBusy("bulk");
    const res = await fetch("/api/bff/admin/allowed-users/bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ emails }),
    });
    const body: { added: string[]; failed: { email: string; error: string }[] } =
      await res.json();
    setBulkResult(
      `Added ${body.added.length}${body.failed.length ? `, ${body.failed.length} failed` : ""}.`,
    );
    setBulkEmails("");
    setBusy(null);
    router.refresh();
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Beta Capacity</CardTitle>
          <CardDescription>
            {betaCapacity.current_allowed} / {betaCapacity.max_beta_users}{" "}
            allowed
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Progress value={pct} />
          <form onSubmit={saveMaxBeta} className="flex gap-2">
            <Input
              type="number"
              min={0}
              step={10}
              value={maxBeta}
              onChange={(e) => setMaxBeta(e.target.value)}
              className="w-28"
            />
            <Button type="submit" size="sm" disabled={busy === "beta"}>
              Update Limit
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Pending Login Requests</CardTitle>
          <CardDescription>
            {loginRequests.length === 0
              ? "None"
              : `${loginRequests.length} awaiting review`}
          </CardDescription>
        </CardHeader>
        {loginRequests.length > 0 && (
          <CardContent className="flex flex-col gap-2">
            {loginRequests.map((req) => (
              <div
                key={req.email}
                className="flex items-center justify-between gap-2 rounded-lg border border-border px-2.5 py-1.5"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">
                    {req.email}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {req.name || "N/A"} · {req.attempt_count} attempt
                    {req.attempt_count === 1 ? "" : "s"}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1.5">
                  <Button
                    size="sm"
                    onClick={() => approveRequest(req.email)}
                    disabled={busy === `approve-${req.email}`}
                  >
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => dismissRequest(req.email)}
                    disabled={busy === `dismiss-${req.email}`}
                  >
                    Dismiss
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        )}
      </Card>

      <Card className="sm:col-span-2">
        <CardHeader>
          <CardTitle>Bulk Import Allowlist</CardTitle>
          <CardDescription>One email per line.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submitBulkImport} className="flex flex-col gap-2">
            <textarea
              value={bulkEmails}
              onChange={(e) => setBulkEmails(e.target.value)}
              placeholder={"a@example.com\nb@example.com"}
              rows={4}
              className="w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            />
            <div className="flex items-center gap-3">
              <Button type="submit" size="sm" disabled={busy === "bulk"}>
                Import
              </Button>
              {bulkResult && (
                <span className="text-sm text-muted-foreground">
                  {bulkResult}
                </span>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
