import type { Metadata } from "next";

import { apiFetch } from "@/lib/api";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export const metadata: Metadata = { title: "Admin · Audit Log" };

type AuditEntry = {
  id: number;
  user_id: number;
  email: string;
  changed_from: string | null;
  changed_to: string;
  changed_at: string;
  changed_by: string | null;
  reason: string | null;
};

export default async function AdminAuditPage() {
  const res = await apiFetch("/admin/audit?limit=100");
  const { entries }: { entries: AuditEntry[] } = await res.json();

  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No subscription changes recorded yet.
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Changed At</TableHead>
          <TableHead>User Email</TableHead>
          <TableHead>From</TableHead>
          <TableHead>To</TableHead>
          <TableHead>Changed By</TableHead>
          <TableHead>Reason</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map((e) => (
          <TableRow key={e.id}>
            <TableCell className="text-muted-foreground">
              {new Date(e.changed_at).toLocaleString()}
            </TableCell>
            <TableCell>{e.email}</TableCell>
            <TableCell className="text-muted-foreground">
              {e.changed_from ?? "—"}
            </TableCell>
            <TableCell>{e.changed_to}</TableCell>
            <TableCell className="text-muted-foreground">
              {e.changed_by ?? "—"}
            </TableCell>
            <TableCell className="max-w-64 truncate text-muted-foreground">
              {e.reason ?? "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
