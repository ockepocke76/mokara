"use client";

import { useEffect, useRef, useState } from "react";

/** Renders a Mermaid diagram client-side (old app's render_mermaid). */
export function MermaidChart({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({ startOnLoad: false, theme: "neutral" });
        const { svg } = await mermaid.render(
          `mermaid-${Math.random().toString(36).slice(2)}`,
          code,
        );
        if (!cancelled && ref.current) ref.current.innerHTML = svg;
      } catch {
        if (!cancelled) setError(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code]);

  if (error) {
    return (
      <pre className="overflow-x-auto rounded-lg border bg-secondary p-4 text-xs">
        {code}
      </pre>
    );
  }
  return <div ref={ref} className="overflow-x-auto [&_svg]:mx-auto" />;
}
