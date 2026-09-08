"use client";

/** Simulation preview: two mini charts + category badge + quick stats.
 *  Web port of ui/simulation_preview_card.py. */
import type { Data, Layout } from "plotly.js";

import { Chart } from "@/components/chart";

export type SimPreview = {
  simulation_hash: string;
  figures: {
    portfolio?: { data: Data[]; layout: Partial<Layout> };
    cashflow?: { data: Data[]; layout: Partial<Layout> };
  };
  category: string;
  stats: { label: string; value: string }[];
};

const CATEGORY_EMOJI: Record<string, string> = {
  WITHDRAWAL_ONLY: "🔴",
  CONTRIBUTION_ONLY: "🟢",
  HYBRID: "🟠",
  UNKNOWN: "⚪",
};

export function SimPreviewCard({ preview }: { preview: SimPreview }) {
  const categoryDisplay = preview.category
    .split("_")
    .map((w) => w[0] + w.slice(1).toLowerCase())
    .join(" ");

  return (
    <div>
      <div className="grid gap-3 sm:grid-cols-2">
        {preview.figures.portfolio && (
          <div>
            <p className="mb-1 text-xs text-muted-foreground">
              📊 Portfolio Value (Median Path)
            </p>
            <Chart
              className="h-56"
              data={preview.figures.portfolio.data}
              layout={{
                ...preview.figures.portfolio.layout,
                autosize: true,
                width: undefined,
              }}
            />
          </div>
        )}
        {preview.figures.cashflow && (
          <div>
            <p className="mb-1 text-xs text-muted-foreground">
              💰 Yearly Cash Flow
            </p>
            <Chart
              className="h-56"
              data={preview.figures.cashflow.data}
              layout={{
                ...preview.figures.cashflow.layout,
                autosize: true,
                width: undefined,
              }}
            />
          </div>
        )}
      </div>
      <div className="mt-3 border-t pt-2">
        <p className="text-xs text-muted-foreground">
          {CATEGORY_EMOJI[preview.category] ?? "⚪"}{" "}
          <strong>{categoryDisplay}</strong> Strategy
        </p>
        <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {preview.stats.map((s) => (
            <div key={s.label} className="leading-tight">
              <span className="text-xs text-muted-foreground">{s.label}</span>
              <br />
              <span className="text-sm font-semibold">{s.value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
