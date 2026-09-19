import type { Metadata } from "next";

import { apiFetch } from "@/lib/api";
import { AccessPanel, type BetaCapacity, type LoginRequest } from "./access-panel";
import { UsersTable, type AdminUser } from "./users-table";

export const metadata: Metadata = { title: "Admin · Users" };

export default async function AdminUsersPage() {
  const [usersRes, betaRes, requestsRes] = await Promise.all([
    apiFetch("/admin/users"),
    apiFetch("/admin/system-settings/max-beta-users"),
    apiFetch("/admin/login-requests"),
  ]);
  const usersBody: { users: AdminUser[]; tiers: string[] } =
    await usersRes.json();
  const betaCapacity: BetaCapacity = await betaRes.json();
  const requestsBody: { requests: LoginRequest[] } = await requestsRes.json();

  return (
    <div className="flex flex-col gap-6">
      <AccessPanel
        betaCapacity={betaCapacity}
        loginRequests={requestsBody.requests}
      />
      <UsersTable users={usersBody.users} tiers={usersBody.tiers} />
    </div>
  );
}
