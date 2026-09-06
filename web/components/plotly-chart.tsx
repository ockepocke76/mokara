"use client";

/**
 * Client-side Plotly wrapper. Loaded dynamically (Plotly can't run on the
 * server) with a skeleton while the bundle streams in.
 *
 * Uses plotly.js-dist-min via a factory so we don't ship the full build.
 */
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import type { Layout, Data, Config } from "plotly.js";

const Plot = createPlotlyComponent(Plotly);

export type PlotlyChartProps = {
  data: Data[];
  layout?: Partial<Layout>;
  config?: Partial<Config>;
  className?: string;
};

const BASE_LAYOUT: Partial<Layout> = {
  autosize: true,
  margin: { l: 48, r: 16, t: 32, b: 40 },
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { family: "var(--font-geist-sans), sans-serif", size: 12 },
};

export default function PlotlyChart({
  data,
  layout,
  config,
  className,
}: PlotlyChartProps) {
  return (
    <div className={className}>
      <Plot
        data={data}
        layout={{ ...BASE_LAYOUT, ...layout }}
        config={{ displayModeBar: false, responsive: true, ...config }}
        useResizeHandler
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
}
