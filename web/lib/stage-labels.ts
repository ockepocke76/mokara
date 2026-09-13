/**
 * Designer stage rail: keys and user-facing labels. A leaf module (no
 * imports) so surfaces like the dashboard's marketing section can use the
 * labels without pulling in the run-model machinery.
 */

export const STAGES = [
  "understanding",
  "examples",
  "blueprint",
  "code",
  "checks",
  "test_flight",
  "behavior",
  "decision",
] as const;

export type StageKey = (typeof STAGES)[number];

export const STAGE_LABELS: Record<StageKey, string> = {
  understanding: "Understanding",
  examples: "Studying examples",
  blueprint: "Blueprint",
  code: "Writing code",
  checks: "Safety checks",
  test_flight: "Test flight",
  behavior: "Behavior review",
  decision: "Your decision",
};
