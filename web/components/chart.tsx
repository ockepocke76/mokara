"use client";

import dynamic from "next/dynamic";

import { Skeleton } from "@/components/ui/skeleton";
import type { PlotlyChartProps } from "@/components/plotly-chart";

/** SSR-safe Plotly chart. Use this everywhere instead of PlotlyChart. */
export const Chart = dynamic(() => import("@/components/plotly-chart"), {
  ssr: false,
  loading: () => <Skeleton className="h-full min-h-64 w-full" />,
}) as React.ComponentType<PlotlyChartProps>;
