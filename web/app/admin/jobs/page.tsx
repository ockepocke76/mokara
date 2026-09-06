import type { Metadata } from "next";

import { apiFetch } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export const metadata: Metadata = { title: "Admin · Jobs" };

type Job = {
  id: string;
  job_type: string;
  status: string;
  created_at: string | null;
  completed_at: string | null;
  retry_count: number | null;
  error_message: string | null;
};

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  COMPLETED: "secondary",
  PROCESSING: "default",
  PENDING: "outline",
  FAILED: "destructive",
};

export default async function AdminJobsPage() {
  const res = await apiFetch("/admin/jobs?limit=100");
  const { jobs }: { jobs: Job[] } = await res.json();

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Type</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Created</TableHead>
          <TableHead>Completed</TableHead>
          <TableHead className="text-right">Retries</TableHead>
          <TableHead>Error</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((j) => (
          <TableRow key={j.id}>
            <TableCell className="font-mono text-xs">{j.job_type}</TableCell>
            <TableCell>
              <Badge variant={STATUS_VARIANT[j.status] ?? "outline"}>
                {j.status}
              </Badge>
            </TableCell>
            <TableCell className="text-muted-foreground">
              {j.created_at ? new Date(j.created_at).toLocaleString() : "—"}
            </TableCell>
            <TableCell className="text-muted-foreground">
              {j.completed_at ? new Date(j.completed_at).toLocaleString() : "—"}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {j.retry_count ?? 0}
            </TableCell>
            <TableCell className="max-w-64 truncate text-xs text-destructive">
              {j.error_message ?? ""}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
