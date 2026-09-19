import type { Metadata } from "next";

import { apiFetch } from "@/lib/api";
import { DemoContentLists, type DemoSimulation, type DemoStrategy } from "./demo-content-lists";

export const metadata: Metadata = { title: "Admin · Demo Content" };

export default async function AdminDemoContentPage() {
  const res = await apiFetch("/admin/demo-content");
  const body: { simulations: DemoSimulation[]; strategies: DemoStrategy[] } =
    await res.json();

  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-muted-foreground">
        Mark simulations and strategies owned by ADMIN-tier accounts as
        visible to anonymous, logged-out visitors.
      </p>
      <DemoContentLists
        simulations={body.simulations}
        strategies={body.strategies}
      />
    </div>
  );
}
