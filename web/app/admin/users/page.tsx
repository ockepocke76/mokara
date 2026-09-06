import type { Metadata } from "next";

import { apiFetch } from "@/lib/api";
import { UsersTable, type AdminUser } from "./users-table";

export const metadata: Metadata = { title: "Admin · Users" };

export default async function AdminUsersPage() {
  const res = await apiFetch("/admin/users");
  const body: { users: AdminUser[]; tiers: string[] } = await res.json();
  return <UsersTable users={body.users} tiers={body.tiers} />;
}
