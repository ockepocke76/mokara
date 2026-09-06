"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const CURRENCIES = ["SEK", "USD", "EUR"];

export function SettingsForm({ currency }: { currency: string }) {
  const router = useRouter();
  const [value, setValue] = useState(currency);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );

  async function save() {
    setState("saving");
    const res = await fetch("/api/bff/me/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ currency: value }),
    });
    setState(res.ok ? "saved" : "error");
    if (res.ok) router.refresh();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Preferences</CardTitle>
        <CardDescription>
          Display currency for simulations and reports.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-1.5">
          <Label>Currency</Label>
          <Select value={value} onValueChange={setValue}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CURRENCIES.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {state === "error" && (
          <p className="text-sm text-destructive">Failed to save.</p>
        )}
        <Button
          onClick={save}
          disabled={state === "saving"}
          className="self-start"
        >
          {state === "saving"
            ? "Saving…"
            : state === "saved"
              ? "Saved ✓"
              : "Save"}
        </Button>
      </CardContent>
    </Card>
  );
}
