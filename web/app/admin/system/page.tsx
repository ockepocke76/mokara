import type { Metadata } from "next";

import { apiFetch } from "@/lib/api";
import { MigrationsPanel, type MigrationStatus } from "./migrations-panel";
import { SystemActions } from "./system-actions";

export const metadata: Metadata = { title: "Admin · System" };

export default async function AdminSystemPage() {
  const res = await apiFetch("/admin/migrations");
  const status: MigrationStatus = await res.json();

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <MigrationsPanel status={status} />
      <SystemActions />
    </div>
  );
}
