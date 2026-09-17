"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Renders a Mermaid diagram client-side (old app's render_mermaid). The
 * mermaid bundle is loaded and rendered only once the container scrolls near
 * the viewport — a hidden container (e.g. inside a closed <details>) never
 * intersects, so rendering defers until it is revealed.
 */
export function MermaidChart({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      const id = requestAnimationFrame(() => setInView(true));
      return () => cancelAnimationFrame(id);
    }
    const observer = new IntersectionObserver(
      (entries, obs) => {
        if (entries.some((e) => e.isIntersecting)) {
          obs.disconnect();
          setInView(true);
        }
      },
      { rootMargin: "100px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!inView) return;
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        // securityLevel stays pinned to "strict": the rendered SVG goes into
        // innerHTML below, and lineage-graph labels carry USER-AUTHORED text
        // (evolve prompts). "strict" makes mermaid DOMPurify labels; loosening
        // it (e.g. for clickable nodes) would turn every label in the app
        // into an HTML-injection sink — don't, without a different sink.
        mermaid.initialize({
          startOnLoad: false,
          theme: "neutral",
          securityLevel: "strict",
        });
        const { svg } = await mermaid.render(
          `mermaid-${Math.random().toString(36).slice(2)}`,
          code,
        );
        if (!cancelled && ref.current) ref.current.innerHTML = svg;
      } catch (err) {
        console.error("Mermaid render failed:", err);
        if (!cancelled) setError(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, inView]);

  if (error) {
    return (
      <pre className="overflow-x-auto rounded-lg border bg-secondary p-4 text-xs">
        {code}
      </pre>
    );
  }
  return <div ref={ref} className="overflow-x-auto [&_svg]:mx-auto" />;
}
