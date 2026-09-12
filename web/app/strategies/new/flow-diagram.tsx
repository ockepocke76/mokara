"use client";

import { useState } from "react";

import { MermaidChart } from "@/components/mermaid-chart";

import { STAGE_LABELS } from "../model";

/**
 * How-it-works flowchart for the strategy designer, mirroring the server
 * generation graph (api/app/agents/graph.py) including its rework loop
 * (MAX_ATTEMPTS) and refine loop (MAX_REVISIONS) — keep the counts below in
 * sync with those constants. Stage names come from STAGE_LABELS so the
 * diagram can't drift from the progress rail.
 */
const L = STAGE_LABELS;
const FLOW = `
flowchart TD
    request([Your request]) --> understanding[${L.understanding}<br/>what should it do?]
    understanding -->|something is unclear| clarify{{A couple of<br/>questions for you}}
    clarify -->|your answers, or<br/>your assumptions| examples
    understanding -->|clear enough| examples[${L.examples}]
    examples --> blueprint[${L.blueprint}<br/>rules and parameters]
    blueprint --> code[${L.code}]
    code --> checks[${L.checks}<br/>sandbox and blueprint conformance]
    checks -->|passed| test[${L.test_flight}<br/>quick simulation]
    test -->|ran fine| behavior[${L.behavior}<br/>does it do what the blueprint says?]
    checks -->|problem found| rework[Rework<br/>up to 3 attempts]
    test -->|problem found| rework
    behavior -->|doesn't match| rework
    rework -->|try again| code
    rework -->|attempts exhausted| failed([Failed - last draft kept])
    behavior -->|matches| decision{{${L.decision}}}
    decision -->|save| saved([Strategy saved])
    decision -->|request changes<br/>up to 3 rounds| code
    decision -->|discard| discarded([Discarded])

    classDef you fill:#fef3c7,stroke:#f59e0b,color:#78350f
    classDef good fill:#d1fae5,stroke:#10b981,color:#064e3b
    classDef bad fill:#fee2e2,stroke:#ef4444,color:#7f1d1d
    class clarify,decision you
    class saved good
    class failed,discarded bad
`;

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
        {opened && <MermaidChart code={FLOW} />}
      </div>
    </details>
  );
}
