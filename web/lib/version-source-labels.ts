/** Plain-language labels for STRATEGY_VERSIONS.source — one source of truth
 *  for the Versions list badges and the lineage-graph node labels (leaf
 *  module, same pattern as stage-labels.ts). */
export const VERSION_SOURCE_LABELS: Record<string, string> = {
  create: "created",
  evolve: "evolved",
  edit: "edited",
  revert: "restored",
  backfill: "imported",
};
