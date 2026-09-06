"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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

export function SimulateForm({ schema }: { schema: ParamSchema }) {
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
        setPhase({
          kind: "error",
          message: job.error ?? "Simulation failed",
        });
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

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setPhase({ kind: "submitting" });

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

    const res = await fetch("/api/bff/simulations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        params,
        simulation_name: name || undefined,
      }),
    });
    const body = await res.json();

    if (!res.ok) {
      const detail = Array.isArray(body.detail)
        ? body.detail.join(" ")
        : (body.detail ?? "Failed to start simulation");
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
    // noValidate: engine-side validate_params is authoritative; native number
    // validation rejects legitimate config defaults that sit off step grids.
    <form onSubmit={submit} noValidate className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Strategy</CardTitle>
          {strategy?.description && (
            <CardDescription>{strategy.description}</CardDescription>
          )}
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
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
          {(strategy?.params ?? [])
            .filter((p) => isVisible(p, values))
            .map((p) => (
              <ParamField
                key={p.key}
                spec={p}
                value={values[p.key]}
                onChange={(v) => set(p.key, v)}
              />
            ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Asset model</CardTitle>
          {asset?.description && (
            <CardDescription>{asset.description}</CardDescription>
          )}
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Select
            value={assetKey}
            onValueChange={(v) => {
              setAssetKey(v);
              adoptDefaults(schema.assets.find((a) => a.key === v)?.params ?? []);
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
          {(asset?.params ?? []).map((p) => (
            <ParamField
              key={p.key}
              spec={p}
              value={values[p.key]}
              onChange={(v) => set(p.key, v)}
            />
          ))}
        </CardContent>
      </Card>

      {schema.sections.map((section) => (
        <Card key={section.title}>
          <CardHeader>
            <CardTitle>{section.title}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {section.params.map((p) => (
              <ParamField
                key={p.key}
                spec={p}
                value={values[p.key]}
                onChange={(v) => set(p.key, v)}
              />
            ))}
          </CardContent>
        </Card>
      ))}

      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div className="grid gap-1.5">
            <Label htmlFor="sim-name">Simulation name (optional)</Label>
            <Input
              id="sim-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Trinity 4% on S&P 500"
            />
          </div>

          {phase.kind === "error" && (
            <p className="text-sm text-destructive">{phase.message}</p>
          )}
          {phase.kind === "polling" && (
            <div className="flex flex-col gap-2">
              <Progress value={(phase.value ?? 0) * 100} />
              <p className="text-sm text-muted-foreground">
                {phase.message ?? "Running…"}
              </p>
            </div>
          )}

          <Button type="submit" disabled={busy} size="lg">
            {busy ? "Running…" : "Run simulation"}
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}
