"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export type MigrationStatus = {
  pending: { version: string; preview: string }[];
  applied: { version: string; applied_at: string; file_missing?: boolean }[];
};

type ActionState = { state: "idle" | "busy" | "done" | "error"; note?: string };

export function MigrationsPanel({ status }: { status: MigrationStatus }) {
  const router = useRouter();
  const [run, setRun] = useState<ActionState>({ state: "idle" });
  const [tables, setTables] = useState<string[] | null>(null);
  const [tablesBusy, setTablesBusy] = useState(false);

  const total = status.pending.length + status.applied.filter((a) => !a.file_missing).length;

  async function runMigrations() {
    setRun({ state: "busy" });
    const res = await fetch("/api/bff/admin/migrations/run", { method: "POST" });
    if (res.ok) {
      setRun({ state: "done", note: "Migrations applied." });
      router.refresh();
    } else {
      const body = await res.json().catch(() => ({}));
      setRun({ state: "error", note: body.detail ?? "Failed — see API logs." });
    }
  }

  async function verifySchema() {
    setTablesBusy(true);
    const res = await fetch("/api/bff/admin/migrations/tables");
    const body = await res.json().catch(() => ({ tables: [] }));
    setTables(body.tables ?? []);
    setTablesBusy(false);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Database migrations</CardTitle>
        <CardDescription>
          {total} on disk · {status.applied.length} applied ·{" "}
          {status.pending.length === 0 ? (
            <span className="text-foreground">none pending</span>
          ) : (
            <span className="text-destructive">{status.pending.length} pending</span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {status.pending.length > 0 && (
          <div className="flex flex-col gap-2">
            {status.pending.map((m) => (
              <details key={m.version} className="rounded-lg border border-border px-2.5 py-1.5 text-sm">
                <summary className="cursor-pointer font-mono">{m.version}</summary>
                <pre className="mt-2 overflow-x-auto text-xs text-muted-foreground">
                  {m.preview}
                </pre>
              </details>
            ))}
            <p className="text-xs text-muted-foreground">
              Running modifies the live database — make sure there is a backup.
            </p>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            onClick={runMigrations}
            disabled={run.state === "busy" || status.pending.length === 0}
          >
            {run.state === "busy" ? "Running…" : "Run pending migrations"}
          </Button>
          <Button variant="outline" onClick={verifySchema} disabled={tablesBusy}>
            {tablesBusy ? "Checking…" : "Verify schema"}
          </Button>
          {run.note && (
            <p className={`text-sm ${run.state === "error" ? "text-destructive" : "text-muted-foreground"}`}>
              {run.note}
            </p>
          )}
        </div>

        {tables && (
          <details open className="rounded-lg border border-border px-2.5 py-1.5 text-sm">
            <summary className="cursor-pointer">{tables.length} tables in public schema</summary>
            <ul className="mt-2 columns-2 font-mono text-xs text-muted-foreground sm:columns-3">
              {tables.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </details>
        )}

        <details className="text-sm">
          <summary className="cursor-pointer">Migration history</summary>
          <Table className="mt-2">
            <TableHeader>
              <TableRow>
                <TableHead>Version</TableHead>
                <TableHead>Applied</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {status.applied.map((a) => (
                <TableRow key={a.version}>
                  <TableCell className="font-mono text-xs">{a.version}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {/* Locale formatting differs server vs. browser; this is
                        React's sanctioned escape hatch for timestamps. */}
                    <time dateTime={a.applied_at} suppressHydrationWarning>
                      {new Date(a.applied_at).toLocaleString()}
                    </time>
                  </TableCell>
                  <TableCell>
                    {a.file_missing && (
                      <Badge variant="destructive">file missing</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </details>
      </CardContent>
    </Card>
  );
}
