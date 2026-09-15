"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ParamField } from "@/components/param-field";
import {
  defaultsFor,
  isVisible,
  type ParamSchema,
  type ParamSpec,
} from "@/lib/param-types";

type Phase =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "polling"; jobId: string; hash: string; message?: string; value?: number }
  | { kind: "error"; message: string };

type LimitConflict = {
  message: string;
  to_delete: { history_id: number; name: string | null; created_at: string }[];
};

const SECTION_EMOJI: Record<string, string> = {
  "Simulation Settings": "🎛️",
  "Economic Assumptions": "📈",
  "Tax Settings": "💰",
};

export function SimulateForm({
  schema,
  currency,
}: {
  schema: ParamSchema;
  currency?: string;
}) {
  const router = useRouter();
  const [strategyKey, setStrategyKey] = useState(schema.defaults.strategy);
  const [assetKey, setAssetKey] = useState(schema.defaults.asset_model);
  const [name, setName] = useState("");
  const [values, setValues] = useState<Record<string, unknown>>(() => {
    const strategy = schema.strategies.find(
      (s) => s.key === schema.defaults.strategy,
    );
    const asset = schema.assets.find(
      (a) => a.key === schema.defaults.asset_model,
    );
    return {
      ...defaultsFor(schema.sections.flatMap((s) => s.params)),
      ...defaultsFor(asset?.params ?? []),
      ...defaultsFor(strategy?.params ?? []),
    };
  });
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [conflict, setConflict] = useState<LimitConflict | null>(null);

  const strategy = useMemo(
    () => schema.strategies.find((s) => s.key === strategyKey),
    [schema, strategyKey],
  );
  const asset = useMemo(
    () => schema.assets.find((a) => a.key === assetKey),
    [schema, assetKey],
  );

  function set(key: string, v: unknown) {
    setValues((prev) => ({ ...prev, [key]: v }));
  }

  function adoptDefaults(params: ParamSpec[]) {
    setValues((prev) => ({ ...defaultsFor(params), ...prev }));
  }

  async function poll(jobId: string, hash: string) {
    for (;;) {
      await new Promise((r) => setTimeout(r, 1500));
      const res = await fetch(`/api/bff/jobs/${jobId}`);
      if (!res.ok) continue;
      const job = await res.json();
      if (job.status === "COMPLETED") {
        router.push(`/simulations/${hash}`);
        return;
      }
      if (job.status === "FAILED") {
        setPhase({ kind: "error", message: job.error ?? "Simulation failed" });
        return;
      }
      setPhase({
        kind: "polling",
        jobId,
        hash,
        message: job.progress_message ?? job.status,
        value: job.progress_value ?? undefined,
      });
    }
  }

  function buildParams(): Record<string, unknown> {
    const params: Record<string, unknown> = {
      strategy: strategyKey,
      asset_model: assetKey,
    };
    for (const p of schema.sections.flatMap((s) => s.params)) {
      if (values[p.key] !== undefined) params[p.key] = values[p.key];
    }
    for (const p of asset?.params ?? []) {
      if (values[p.key] !== undefined) params[p.key] = values[p.key];
    }
    for (const p of strategy?.params ?? []) {
      if (!isVisible(p, values)) continue;
      if (values[p.key] !== undefined) params[p.key] = values[p.key];
    }
    return params;
  }

  async function run(replaceOldest: boolean) {
    setPhase({ kind: "submitting" });
    setConflict(null);

    const res = await fetch("/api/bff/simulations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        params: buildParams(),
        simulation_name: name || undefined,
        replace_oldest: replaceOldest,
      }),
    });
    const body = await res.json();

    if (res.status === 409 && body.detail?.to_delete) {
      setPhase({ kind: "idle" });
      setConflict(body.detail as LimitConflict);
      return;
    }
    if (!res.ok) {
      const detail = Array.isArray(body.detail)
        ? body.detail.join(" ")
        : typeof body.detail === "string"
          ? body.detail
          : "Failed to start simulation";
      setPhase({ kind: "error", message: detail });
      return;
    }
    if (body.status === "cached") {
      router.push(`/simulations/${body.simulation_hash}`);
      return;
    }
    setPhase({
      kind: "polling",
      jobId: body.job_id,
      hash: body.simulation_hash,
      message: "Queued…",
    });
    void poll(body.job_id, body.simulation_hash);
  }

  const busy = phase.kind === "submitting" || phase.kind === "polling";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void run(false);
      }}
      noValidate
      className="flex flex-col gap-4"
    >
      <Accordion
        type="multiple"
        defaultValue={["setup", "Simulation Settings"]}
        className="flex flex-col gap-3"
      >
        <AccordionItem value="setup" className="rounded-lg border bg-card px-4">
          <AccordionTrigger className="text-base font-semibold">
            ⚙️ Simulation Settings
          </AccordionTrigger>
          <AccordionContent className="flex flex-col gap-4 pt-1">
            <div className="grid gap-1.5">
              <Label htmlFor="sim-name">Name of Simulation</Label>
              <Input
                id="sim-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Trinity 4% on S&P 500"
              />
            </div>

            <div className="grid gap-1.5">
              <Label>Strategy</Label>
              <Select
                value={strategyKey}
                onValueChange={(v) => {
                  setStrategyKey(v);
                  adoptDefaults(
                    schema.strategies.find((s) => s.key === v)?.params ?? [],
                  );
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {schema.strategies.map((s) => (
                    <SelectItem key={s.key} value={s.key}>
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {strategy?.description && (
                <p className="text-xs text-muted-foreground">
                  {strategy.description}
                </p>
              )}
            </div>

            {(strategy?.params ?? []).filter((p) => isVisible(p, values))
              .length > 0 && (
              <div className="rounded-lg border bg-secondary/40 p-4">
                <p className="mb-3 text-sm font-medium">Strategy Settings</p>
                <div className="flex flex-col gap-4">
                  {(strategy?.params ?? [])
                    .filter((p) => isVisible(p, values))
                    .map((p) => (
                      <ParamField
                        key={p.key}
                        spec={p}
                        value={values[p.key]}
                        onChange={(v) => set(p.key, v)}
                        currency={currency}
                      />
                    ))}
                </div>
              </div>
            )}

            <div className="grid gap-1.5">
              <Label>Asset Model</Label>
              <Select
                value={assetKey}
                onValueChange={(v) => {
                  setAssetKey(v);
                  adoptDefaults(
                    schema.assets.find((a) => a.key === v)?.params ?? [],
                  );
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {schema.assets.map((a) => (
                    <SelectItem key={a.key} value={a.key}>
                      {a.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {asset?.description && (
                <p className="text-xs text-muted-foreground">
                  {asset.description}
                </p>
              )}
            </div>

            {(asset?.params ?? []).length > 0 && (
              <div className="rounded-lg border bg-secondary/40 p-4">
                <p className="mb-3 text-sm font-medium">Asset Settings</p>
                <div className="flex flex-col gap-4">
                  {(asset?.params ?? []).map((p) => (
                    <ParamField
                      key={p.key}
                      spec={p}
                      value={values[p.key]}
                      onChange={(v) => set(p.key, v)}
                      currency={currency}
                    />
                  ))}
                </div>
              </div>
            )}
          </AccordionContent>
        </AccordionItem>

        {schema.sections.map((section) => (
          <AccordionItem
            key={section.title}
            value={section.title}
            className="rounded-lg border bg-card px-4"
          >
            <AccordionTrigger className="text-base font-semibold">
              {SECTION_EMOJI[section.title] ?? "🔧"} {section.title}
            </AccordionTrigger>
            <AccordionContent className="flex flex-col gap-4 pt-1">
              {section.params.map((p) => (
                <ParamField
                  key={p.key}
                  spec={p}
                  value={values[p.key]}
                  onChange={(v) => set(p.key, v)}
                  currency={currency}
                />
              ))}
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>

      <div className="sticky bottom-[calc(3.5rem+env(safe-area-inset-bottom))] -mx-4 border-t bg-background/95 px-4 py-3 backdrop-blur md:bottom-0">
        {phase.kind === "error" && (
          <p className="mb-2 text-sm text-destructive">{phase.message}</p>
        )}
        {phase.kind === "polling" && (
          <div className="mb-2 flex flex-col gap-1">
            <Progress value={(phase.value ?? 0) * 100} />
            <p className="text-sm text-muted-foreground">
              {phase.message ?? "Running…"}
            </p>
          </div>
        )}
        <Button type="submit" disabled={busy} size="lg" className="w-full">
          {busy ? "Running…" : "🚀 Run Simulation"}
        </Button>
      </div>

      <Dialog open={conflict !== null} onOpenChange={() => setConflict(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Simulation limit reached</DialogTitle>
            <DialogDescription>
              {conflict?.message} Running this simulation will permanently
              delete your oldest saved simulation
              {(conflict?.to_delete.length ?? 0) > 1 ? "s" : ""}:
            </DialogDescription>
          </DialogHeader>
          <ul className="list-disc pl-5 text-sm">
            {conflict?.to_delete.map((s) => (
              <li key={s.history_id}>
                {s.name || "Untitled simulation"}{" "}
                <span className="text-muted-foreground">
                  ({new Date(s.created_at).toLocaleDateString()})
                </span>
              </li>
            ))}
          </ul>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConflict(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => void run(true)}
            >
              Delete &amp; run
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </form>
  );
}
