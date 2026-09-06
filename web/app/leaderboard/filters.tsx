"use client";

import { useRouter, useSearchParams } from "next/navigation";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function LeaderboardFilters({
  categories,
  profiles,
  category,
  profile,
}: {
  categories: string[];
  profiles: { key: string; name: string }[];
  category?: string;
  profile: string;
}) {
  const router = useRouter();
  const params = useSearchParams();

  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value === "all") next.delete(key);
    else next.set(key, value);
    router.push(`/leaderboard?${next.toString()}`);
  }

  return (
    <div className="flex gap-2">
      <Select
        value={category ?? "all"}
        onValueChange={(v) => update("category", v)}
      >
        <SelectTrigger className="w-44">
          <SelectValue placeholder="Category" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All categories</SelectItem>
          {categories.map((c) => (
            <SelectItem key={c} value={c}>
              {c
                .split("_")
                .map((w) => w[0] + w.slice(1).toLowerCase())
                .join(" ")}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select value={profile} onValueChange={(v) => update("profile", v)}>
        <SelectTrigger className="w-52">
          <SelectValue placeholder="Weighting profile" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="balanced">Balanced (default)</SelectItem>
          {profiles.map((p) => (
            <SelectItem key={p.key} value={p.key}>
              {p.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
