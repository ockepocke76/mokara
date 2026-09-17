/** Mermaid flowchart labels break on quotes/brackets — keep letters, digits
 *  and light punctuation. This is PARSER-escaping shared by every graph that
 *  feeds user text into Mermaid source; XSS is handled by MermaidChart's
 *  pinned securityLevel "strict". */
export function cleanMermaidLabel(text: string, max: number): string {
  const stripped = text
    .replace(/[^\p{L}\p{N} .,%:;!?'()\-–—/]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
  return stripped.length > max ? `${stripped.slice(0, max - 1)}…` : stripped;
}
