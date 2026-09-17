"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { ParamSpec } from "@/lib/param-types";

function FieldLabel({ spec }: { spec: ParamSpec }) {
  if (!spec.description) return <Label>{spec.label}</Label>;
  return (
    <div className="flex items-center gap-1.5">
      <Label>{spec.label}</Label>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-help text-xs text-muted-foreground">ⓘ</span>
        </TooltipTrigger>
        <TooltipContent className="max-w-72">{spec.description}</TooltipContent>
      </Tooltip>
    </div>
  );
}

export function ParamField({
  spec,
  value,
  onChange,
  currency,
}: {
  spec: ParamSpec;
  value: unknown;
  onChange: (v: unknown) => void;
  currency?: string;
}) {
  if (spec.type === "select") {
    return (
      <div className="grid gap-1.5">
        <FieldLabel spec={spec} />
        <Select
          value={String(value ?? spec.default ?? "")}
          onValueChange={(v) => onChange(v)}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(spec.options ?? []).map((o, i) => (
              <SelectItem key={o} value={o}>
                {spec.captions?.[i] ? `${o} — ${spec.captions[i]}` : o}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  }

  if (spec.type === "boolean") {
    return (
      <div className="flex items-center gap-2">
        <Checkbox
          id={spec.key}
          checked={Boolean(value)}
          onCheckedChange={(c) => onChange(c === true)}
        />
        <Label htmlFor={spec.key} title={spec.description ?? undefined}>
          {spec.label}
        </Label>
      </div>
    );
  }

  if (spec.type === "number") {
    if (spec.min == null && spec.max == null) {
      // No range metadata — e.g. a custom strategy's params, which carry no
      // min/max/step (unlike built-ins). A slider needs real bounds, so
      // fall back to a plain numeric input instead of a nonsense 0-100 range.
      const num = typeof value === "number" ? value : Number(spec.default ?? 0);
      return (
        <div className="grid gap-1.5">
          <FieldLabel spec={spec} />
          <Input
            type="number"
            value={num}
            step="any"
            onChange={(e) => onChange(Number(e.target.value))}
          />
        </div>
      );
    }
    const num = typeof value === "number" ? value : Number(spec.default ?? 0);
    const scale = spec.is_percent ? 100 : 1;
    const display = Math.round(num * scale * 10000) / 10000;
    const min = (spec.min ?? 0) * scale;
    const max = (spec.max ?? 100) * scale;
    const step = (spec.step ?? (spec.is_percent ? 0.001 : 1)) * scale;
    const pct =
      max > min ? Math.min(100, Math.max(0, ((display - min) / (max - min)) * 100)) : 0;
    const bubble = spec.is_percent
      ? `${display}%`
      : spec.is_currency
        ? display.toLocaleString()
        : String(display);

    return (
      <div className="grid gap-1">
        <FieldLabel spec={spec} />
        <div className="flex items-center gap-3">
          <div className="relative flex-1 pt-5">
            {/* Value bubble above the thumb, like the old app's sliders */}
            <span
              className="pointer-events-none absolute top-0 -translate-x-1/2 text-xs font-medium text-primary"
              style={{ left: `${pct}%` }}
            >
              {bubble}
            </span>
            <Slider
              value={[display]}
              min={min}
              max={max}
              step={step}
              onValueChange={([v]) => onChange(v / scale)}
            />
          </div>
          <Input
            type="number"
            className="w-28"
            value={display}
            step="any"
            onChange={(e) => onChange(Number(e.target.value) / scale)}
          />
        </div>
        {spec.is_currency && currency && (
          <p className="text-xs text-muted-foreground">
            → {display.toLocaleString("sv-SE")} {currency}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="grid gap-1.5">
      <FieldLabel spec={spec} />
      <Input
        value={String(value ?? spec.default ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
