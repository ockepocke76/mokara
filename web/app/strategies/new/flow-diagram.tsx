import {
  DESIGNER_FLOW,
  DESIGNER_FLOW_CAPTION,
} from "@/components/designer-flow";
import { MermaidChart } from "@/components/mermaid-chart";

/**
 * Collapsible how-it-works panel for the designer entry form. The chart
 * inside the closed <details> never intersects the viewport, so MermaidChart
 * defers loading the mermaid bundle until the panel is first opened.
 */
export function FlowDiagram() {
  return (
    <details className="rounded-lg border">
      <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium text-muted-foreground hover:text-foreground">
        How the designer works
      </summary>
      <div className="border-t px-4 py-4">
        <p className="mb-3 text-sm text-muted-foreground">
          {DESIGNER_FLOW_CAPTION} Nothing is saved until you decide.
        </p>
        <MermaidChart code={DESIGNER_FLOW} />
      </div>
    </details>
  );
}
