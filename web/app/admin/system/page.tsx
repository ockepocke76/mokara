import type { Metadata } from "next";

import { apiFetch } from "@/lib/api";
import { EvaluationsPanel, type EvaluationStrategies } from "./evaluations-panel";
import { MigrationsPanel, type MigrationStatus } from "./migrations-panel";
import { SystemActions } from "./system-actions";

export const metadata: Metadata = { title: "Admin · System" };

export default async function AdminSystemPage() {
  const [migrationsRes, strategiesRes] = await Promise.all([
    apiFetch("/admin/migrations"),
    apiFetch("/admin/evaluations/strategies"),
  ]);
  const status: MigrationStatus = await migrationsRes.json();
  const strategies: EvaluationStrategies = await strategiesRes.json();

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <MigrationsPanel status={status} />
      <EvaluationsPanel strategies={strategies} />
      <SystemActions />
    </div>
  );
}
