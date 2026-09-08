"use client";

/** Sortino heatmap: strategy × scenario (old _display_scenario_heatmap). */
import type { Data } from "plotly.js";

import { Chart } from "@/components/chart";
import type { Entry } from "./types";

export function ScenarioHeatmap({ entries }: { entries: Entry[] }) {
  const withScenarios = entries.filter((e) => e.scenario_results.length > 0);
  if (withScenarios.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No scenario data available
      </p>
    );
  }

  const scenarioNames = withScenarios[0].scenario_results.map((s) => s.name);
  const strategyNames = withScenarios.map((e) => e.strategy_name);
  const matrix = withScenarios.map((e) =>
    e.scenario_results.map((s) => s.sortino_ratio ?? 0),
  );

  const data: Data[] = [
    {
      type: "heatmap",
      z: matrix,
      x: scenarioNames,
      y: strategyNames,
      colorscale: "RdYlGn",
      zmid: 0,
      text: matrix.map((row) => row.map((v) => v.toFixed(2))),
      texttemplate: "%{text}",
      textfont: { size: 10 },
      colorbar: { title: { text: "Sortino Ratio" } },
    } as unknown as Data,
  ];

  return (
    <Chart
      className="w-full"
      data={data}
      layout={{
        title: { text: "Sortino Ratio by Strategy and Scenario" },
        xaxis: { title: { text: "Market Scenario" } },
        yaxis: { title: { text: "Strategy" }, automargin: true },
        height: 400 + strategyNames.length * 30,
        autosize: true,
      }}
    />
  );
}
