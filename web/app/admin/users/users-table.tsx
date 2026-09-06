"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export type AdminUser = {
  id: number | null;
  email: string;
  name: string | null;
  tier: string;
  allowed: boolean;
  pending_signup?: boolean;
  simulations: number;
  strategies: number;
  joined: string | null;
};

export function UsersTable({
  users,
  tiers,
}: {
  users: AdminUser[];
  tiers: string[];
}) {
  const router = useRouter();
  const [newEmail, setNewEmail] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  async function setTier(userId: number, tier: string) {
    setBusy(`tier-${userId}`);
    await fetch(`/api/bff/admin/users/${userId}/tier`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tier, reason: "admin panel" }),
    });
    setBusy(null);
    router.refresh();
  }

  async function toggleAllowed(user: AdminUser) {
    setBusy(`allow-${user.email}`);
    if (user.allowed) {
      await fetch(
        `/api/bff/admin/allowed-users/${encodeURIComponent(user.email)}`,
        { method: "DELETE" },
      );
    } else {
      await fetch("/api/bff/admin/allowed-users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email }),
      });
    }
    setBusy(null);
    router.refresh();
  }

  async function addAllowed(e: React.FormEvent) {
    e.preventDefault();
    if (!newEmail) return;
    setBusy("add");
    await fetch("/api/bff/admin/allowed-users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: newEmail }),
    });
    setNewEmail("");
    setBusy(null);
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={addAllowed} className="flex max-w-md gap-2">
        <Input
          type="email"
          placeholder="pre-authorize email…"
          value={newEmail}
          onChange={(e) => setNewEmail(e.target.value)}
        />
        <Button type="submit" disabled={busy === "add"}>
          Allow
        </Button>
      </form>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Email</TableHead>
            <TableHead>Tier</TableHead>
            <TableHead>Access</TableHead>
            <TableHead className="text-right">Sims</TableHead>
            <TableHead className="text-right">Strategies</TableHead>
            <TableHead>Joined</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((u) => (
            <TableRow key={u.email}>
              <TableCell>
                <span className="font-medium">{u.email}</span>
                {u.pending_signup && (
                  <Badge variant="outline" className="ml-2">
                    pending signup
                  </Badge>
                )}
              </TableCell>
              <TableCell>
                {u.id === null ? (
                  <span className="text-muted-foreground">—</span>
                ) : (
                  <Select
                    value={u.tier}
                    onValueChange={(t) => setTier(u.id!, t)}
                    disabled={busy === `tier-${u.id}`}
                  >
                    <SelectTrigger className="h-8 w-36">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {tiers.map((t) => (
                        <SelectItem key={t} value={t}>
                          {t}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </TableCell>
              <TableCell>
                <Button
                  variant={u.allowed ? "outline" : "secondary"}
                  size="sm"
                  onClick={() => toggleAllowed(u)}
                  disabled={busy === `allow-${u.email}`}
                >
                  {u.allowed ? "Revoke" : "Allow"}
                </Button>
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {u.simulations}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {u.strategies}
              </TableCell>
              <TableCell className="text-muted-foreground">
                {u.joined ? new Date(u.joined).toLocaleDateString() : "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
