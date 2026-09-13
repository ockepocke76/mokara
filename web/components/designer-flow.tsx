import Link from "next/link";

import { STAGE_LABELS } from "@/lib/stage-labels";
import { MermaidChart } from "@/components/mermaid-chart";
import { Button } from "@/components/ui/button";

/**
 * The strategy-designer flowchart, shared by the designer page and the
 * home/landing marketing section. Mirrors the server generation graph
 * (api/app/agents/graph.py) including its rework loop (MAX_ATTEMPTS) and
 * refine loop (MAX_REVISIONS) — keep the counts below in sync with those
 * constants. Stage names come from STAGE_LABELS so the diagram can't drift
 * from the designer's progress rail.
 */
const L = STAGE_LABELS;
export const DESIGNER_FLOW = `
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

/** Legend for the diagram's amber "needs you" steps — shared so the diagram
 * and its caption can't drift apart across surfaces. */
export const DESIGNER_FLOW_CAPTION =
  "Amber steps pause and wait for you; everything else runs on its own.";

/** Marketing section for the landing page and logged-in home: what the
 * AI designer is, the flowchart, and a call to action. */
export function DesignerFlowSection({ authenticated }: { authenticated: boolean }) {
  return (
    <section className={authenticated ? "mb-8 border-t pt-8" : "mb-10"}>
      <h2 className="mb-3 text-lg font-semibold">
        🤖 Inside the AI Strategy Designer
      </h2>
      <p className="mb-3 text-sm text-muted-foreground">
        Describe the strategy you want in plain English — an agentic AI
        workflow, not a single prompt, turns it into working, tested code.
      </p>
      <div className="mb-4 flex flex-col gap-1 text-sm">
        <p>🧠 <strong>Understands your goal</strong> — and asks you before it assumes</p>
        <p>📐 <strong>Studies proven examples</strong>, then drafts a blueprint you can read</p>
        <p>🛡️ <strong>Writes the code</strong> and puts it through safety checks and a Monte Carlo test flight</p>
        <p>✅ <strong>You get the final say</strong> — nothing is saved until you approve it</p>
      </div>
      <div className="rounded-lg border px-4 py-4">
        <div className="min-h-64">
          <MermaidChart code={DESIGNER_FLOW} />
        </div>
        <p className="mt-2 text-center text-xs text-muted-foreground">
          {DESIGNER_FLOW_CAPTION}
        </p>
      </div>
      <Button asChild size="sm" className="mt-3">
        <Link href={authenticated ? "/strategies/new" : "/login"}>
          {authenticated ? "✨ Design a strategy" : "🔑 Login to design yours"}
        </Link>
      </Button>
    </section>
  );
}
