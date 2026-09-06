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
import type { ParamSpec } from "@/lib/param-types";

export function ParamField({
  spec,
  value,
  onChange,
}: {
  spec: ParamSpec;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  if (spec.type === "select") {
    return (
      <div className="grid gap-1.5">
        <Label title={spec.description ?? undefined}>{spec.label}</Label>
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
    const num = typeof value === "number" ? value : Number(spec.default ?? 0);
    const scale = spec.is_percent ? 100 : 1;
    const display = Math.round(num * scale * 10000) / 10000;
    const min = (spec.min ?? 0) * scale;
    const max = (spec.max ?? 100) * scale;
    const step = (spec.step ?? (spec.is_percent ? 0.001 : 1)) * scale;

    return (
      <div className="grid gap-1.5">
        <div className="flex items-center justify-between">
          <Label title={spec.description ?? undefined}>{spec.label}</Label>
          <span className="text-xs tabular-nums text-muted-foreground">
            {spec.is_percent
              ? `${display}%`
              : spec.is_currency
                ? display.toLocaleString()
                : display}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <Slider
            value={[display]}
            min={min}
            max={max}
            step={step}
            onValueChange={([v]) => onChange(v / scale)}
            className="flex-1"
          />
          <Input
            type="number"
            className="w-28"
            value={display}
            step="any"
            onChange={(e) => onChange(Number(e.target.value) / scale)}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-1.5">
      <Label title={spec.description ?? undefined}>{spec.label}</Label>
      <Input
        value={String(value ?? spec.default ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
