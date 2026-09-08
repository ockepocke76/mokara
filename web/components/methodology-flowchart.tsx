import { apiFetch } from "@/lib/api";
import { MermaidChart } from "@/components/mermaid-chart";

async function fetchFlowchart(): Promise<{
  description: string;
  mermaid: string;
} | null> {
  try {
    const res = await apiFetch("/methodology/flowchart");
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/** Server wrapper: fetches the engine's simulation flowchart (Mermaid). */
export async function MethodologyFlowchart() {
  const body = await fetchFlowchart();
  if (!body) return null;
  return (
    <div className="not-prose my-4">
      <p className="mb-3 text-sm">{body.description}</p>
      <MermaidChart code={body.mermaid} />
    </div>
  );
}
