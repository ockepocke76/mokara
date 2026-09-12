"use client";

import { useState } from "react";

import { DESIGNER_FLOW } from "@/components/designer-flow";
import { MermaidChart } from "@/components/mermaid-chart";

/** Collapsible how-it-works panel for the designer entry form. */
export function FlowDiagram() {
  // Mount the chart only once the panel is first opened, so the entry form
  // never pays for the mermaid bundle when the section stays collapsed.
  const [opened, setOpened] = useState(false);
  return (
    <details
      className="rounded-lg border"
      onToggle={(e) => e.currentTarget.open && setOpened(true)}
    >
      <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium text-muted-foreground hover:text-foreground">
        How the designer works
      </summary>
      <div className="border-t px-4 py-4">
        <p className="mb-3 text-sm text-muted-foreground">
          Amber steps pause and wait for you; everything else runs on its own.
          Nothing is saved until you decide.
        </p>
        {opened && <MermaidChart code={DESIGNER_FLOW} />}
      </div>
    </details>
  );
}
