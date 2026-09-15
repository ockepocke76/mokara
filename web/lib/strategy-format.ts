/** Formatting helpers for strategy metadata shared across pages. */

/** "WITHDRAWAL_ONLY" -> "Withdrawal Only" */
export function categoryLabel(category: string | null): string {
  if (!category) return "—";
  return category
    .split("_")
    .map((w) => w[0] + w.slice(1).toLowerCase())
    .join(" ");
}
