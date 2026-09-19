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

export const metadata: Metadata = { title: "Admin · Tier Configuration" };

type Tier = {
  id: string;
  display_name: string;
  description: string;
  badge: string;
  color: string;
  max_simulations: number | string;
  max_strategies: number | string;
  price_sek_monthly: number | null;
  price_sek_annual: number | null;
  features: Record<string, boolean>;
};

export default async function AdminTiersPage() {
  const res = await apiFetch("/admin/tiers");
  const { tiers }: { tiers: Tier[] } = await res.json();

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Tier configuration is managed in code
        (<code className="font-mono">api/tier_config/limits.py</code>) — this
        is a read-only view.
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead />
            <TableHead>ID</TableHead>
            <TableHead>Name</TableHead>
            <TableHead className="text-right">Price / mo (SEK)</TableHead>
            <TableHead className="text-right">Simulations</TableHead>
            <TableHead className="text-right">Strategies</TableHead>
            <TableHead>Description</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tiers.map((t) => (
            <TableRow key={t.id}>
              <TableCell>{t.badge}</TableCell>
              <TableCell className="font-mono text-xs">{t.id}</TableCell>
              <TableCell>{t.display_name}</TableCell>
              <TableCell className="text-right tabular-nums">
                {t.price_sek_monthly ?? "—"}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {t.max_simulations}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {t.max_strategies}
              </TableCell>
              <TableCell className="max-w-96 text-muted-foreground">
                {t.description}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <details className="rounded-lg border border-border p-3 text-sm">
        <summary className="cursor-pointer font-medium">
          View Raw Configuration
        </summary>
        <pre className="mt-2 overflow-x-auto text-xs text-muted-foreground">
          {JSON.stringify(tiers, null, 2)}
        </pre>
      </details>
    </div>
  );
}
