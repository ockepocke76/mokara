import type { Metadata } from "next";

import { apiFetch } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LeaderboardFilters } from "./filters";

export const metadata: Metadata = { title: "Leaderboard" };

type Entry = {
  rank: number;
  id: number;
  strategy_name: string;
  category: string | null;
  is_custom: boolean;
  author: string | null;
  score: number | null;
};

type Meta = {
  categories: string[];
  profiles: { key: string; name: string }[];
};

const MEDALS = ["🥇", "🥈", "🥉"];

function categoryLabel(category: string | null): string {
  if (!category) return "—";
  return category
    .split("_")
    .map((w) => w[0] + w.slice(1).toLowerCase())
    .join(" ");
}

export default async function LeaderboardPage({
  searchParams,
}: {
  searchParams: Promise<{ category?: string; profile?: string }>;
}) {
  const { category, profile = "balanced" } = await searchParams;

  const qs = new URLSearchParams({ profile, limit: "50" });
  if (category) qs.set("category", category);

  const [metaRes, boardRes] = await Promise.all([
    apiFetch("/leaderboard/meta"),
    apiFetch(`/leaderboard?${qs}`),
  ]);
  const meta: Meta = await metaRes.json();
  const board: { entries: Entry[] } = await boardRes.json();

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-10">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Leaderboard</h1>
          <p className="text-sm text-muted-foreground">
            Strategy rankings by evaluated excellence score.
          </p>
        </div>
        <LeaderboardFilters
          categories={meta.categories}
          profiles={meta.profiles}
          category={category}
          profile={profile}
        />
      </div>

      {board.entries.length === 0 ? (
        <p className="py-16 text-center text-muted-foreground">
          No evaluated strategies yet
          {category ? ` in ${categoryLabel(category)}` : ""}.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-14">#</TableHead>
              <TableHead>Strategy</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Author</TableHead>
              <TableHead className="text-right">Score</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {board.entries.map((e) => (
              <TableRow key={e.id}>
                <TableCell className="text-lg">
                  {MEDALS[e.rank - 1] ?? e.rank}
                </TableCell>
                <TableCell className="font-medium">
                  {e.strategy_name}
                  {e.is_custom && (
                    <Badge variant="secondary" className="ml-2">
                      community
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {categoryLabel(e.category)}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {e.author ?? "Mokara"}
                </TableCell>
                <TableCell className="text-right font-mono">
                  {e.score?.toFixed(1) ?? "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </main>
  );
}
