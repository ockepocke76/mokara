"use client";

import { useEffect, useState } from "react";
import type { Data, Layout } from "plotly.js";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Chart } from "@/components/chart";

export type AssetInfo = {
  key: string;
  name: string;
  ticker: string | null;
  type: string | null;
  description: string | null;
  params: { label: string; value: string; description: string | null }[];
};

type Figure = { data: Data[]; layout: Partial<Layout> };

export function AssetExplorer({ assets }: { assets: AssetInfo[] }) {
  const [selectedKey, setSelectedKey] = useState(assets[0]?.key ?? "");
  const [figures, setFigures] = useState<Record<string, Figure | "loading" | "error">>({});

  const asset = assets.find((a) => a.key === selectedKey);
  const figure = figures[selectedKey];

  useEffect(() => {
    if (!selectedKey || figures[selectedKey]) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      setFigures((prev) =>
        prev[selectedKey] ? prev : { ...prev, [selectedKey]: "loading" },
      );
      fetch(`/api/bff/assets/${selectedKey}/figure`)
        .then(async (res) => {
          if (!res.ok) throw new Error(String(res.status));
          const body = await res.json();
          if (!cancelled)
            setFigures((prev) => ({ ...prev, [selectedKey]: body.figure }));
        })
        .catch(() => {
          if (!cancelled)
            setFigures((prev) => ({ ...prev, [selectedKey]: "error" }));
        });
    }, 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey]);

  if (!asset) return null;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid max-w-md gap-1.5">
        <label className="text-sm font-medium">Select an asset to view</label>
        <Select value={selectedKey} onValueChange={setSelectedKey}>
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {assets.map((a) => (
              <SelectItem key={a.key} value={a.key}>
                {a.ticker ? `${a.name} (${a.ticker})` : a.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="border-t pt-4">
        <h2 className="text-xl font-semibold">{asset.name}</h2>
        <p className="mt-1 text-sm">
          <strong>Ticker:</strong> {asset.ticker ?? "N/A"}
        </p>
        {asset.description && (
          <blockquote className="mt-2 border-l-2 pl-3 text-sm text-muted-foreground">
            {asset.description}
          </blockquote>
        )}

        {asset.params.length > 0 ? (
          <div className="mt-4">
            <p className="mb-2 text-sm font-semibold">
              Configurable Model Parameters:
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {asset.params.map((p) => (
                <div key={p.label} className="rounded-md border px-3 py-2">
                  <div className="flex items-center gap-1.5">
                    <p className="text-xs text-muted-foreground">{p.label}</p>
                    {p.description && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className="cursor-help text-xs text-muted-foreground">
                            ⓘ
                          </span>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-72">
                          {p.description}
                        </TooltipContent>
                      </Tooltip>
                    )}
                  </div>
                  <p className="text-sm font-medium tabular-nums">{p.value}</p>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="mt-3 text-xs text-muted-foreground">
            No configurable parameters for this model.
          </p>
        )}

        <div className="mt-6">
          {figure === "loading" || figure === undefined ? (
            <Skeleton className="h-96 w-full" />
          ) : figure === "error" ? (
            <p className="text-sm text-muted-foreground">
              Could not load price data for this asset.
            </p>
          ) : (
            <Chart
              className="h-[450px]"
              data={figure.data}
              layout={{ ...figure.layout, autosize: true, width: undefined }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
