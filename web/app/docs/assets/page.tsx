import type { Metadata } from "next";

import { apiFetch } from "@/lib/api";
import { AssetExplorer, type AssetInfo } from "./asset-explorer";

export const metadata: Metadata = { title: "Assets" };

export default async function AssetsPage() {
  const res = await apiFetch("/assets");
  const { assets }: { assets: AssetInfo[] } = await res.json();

  return (
    <div>
      <h1 className="mb-1 text-3xl font-bold tracking-tight">
        💹 Asset Model Descriptions
      </h1>
      <p className="mb-6 text-sm text-muted-foreground">
        This section provides details on the different asset models available
        for the simulation, along with key charts illustrating their historical
        characteristics.
      </p>
      <AssetExplorer assets={assets} />
    </div>
  );
}
