/**
 * Brand chart theme — mirrors the engine's reporting/color_scheme.py
 * LightChartColors so bespoke charts match the report charts.
 */
import type { Layout } from "plotly.js";

export const CHART = {
  plotBg: "#f8f9fa",
  grid: "#dee2e6",
  font: "#212529",
  median: "#e74c3c",
  mean: "#f1c40f",
  p25: "#9b59b6",
  p75: "#2ecc71",
  simulationPath: "#3498db",
  iqrFill: "rgba(0, 121, 107, 0.15)",
  primary: "#00796b",
  brandOrange: "#ff6b35",
  navy: "#2e4057",
} as const;

export const brandLayout: Partial<Layout> = {
  autosize: true,
  margin: { l: 56, r: 16, t: 32, b: 40 },
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: CHART.plotBg,
  font: { family: "var(--font-geist-sans), sans-serif", size: 12, color: CHART.font },
  xaxis: { gridcolor: CHART.grid, zerolinecolor: CHART.grid },
  yaxis: { gridcolor: CHART.grid, zerolinecolor: CHART.grid },
  colorway: [CHART.simulationPath, CHART.median, CHART.p75, CHART.p25, CHART.mean],
};
