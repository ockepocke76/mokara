export type ParamSpec = {
  key: string;
  label: string;
  description?: string | null;
  default?: unknown;
  type: "select" | "boolean" | "number" | "text";
  options?: string[];
  captions?: string[];
  min?: number | null;
  max?: number | null;
  step?: number | null;
  is_percent?: boolean;
  is_currency?: boolean;
  visible_if?: { param: string; equals?: string; truthy?: boolean };
};

export type StrategySpec = {
  key: string;
  name: string;
  description?: string | null;
  params: ParamSpec[];
  group?: "builtin" | "mine" | "community";
  is_custom?: boolean;
  disabled?: boolean;
  disabled_reason?: string | null;
};

export type AssetSpec = {
  key: string;
  name: string;
  type?: string | null;
  description?: string | null;
  params: ParamSpec[];
};

export type ParamSchema = {
  strategies: StrategySpec[];
  assets: AssetSpec[];
  sections: { title: string; params: ParamSpec[] }[];
  defaults: { strategy: string; asset_model: string };
};

export function defaultsFor(params: ParamSpec[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const p of params) {
    if (p.default !== undefined && p.default !== null) out[p.key] = p.default;
  }
  return out;
}

export function isVisible(
  p: ParamSpec,
  values: Record<string, unknown>,
): boolean {
  if (!p.visible_if) return true;
  const v = values[p.visible_if.param];
  if (p.visible_if.equals !== undefined) return v === p.visible_if.equals;
  if (p.visible_if.truthy) return Boolean(v);
  return true;
}
