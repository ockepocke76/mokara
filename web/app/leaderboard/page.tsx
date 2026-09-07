import type { Metadata } from "next";

import { apiFetch } from "@/lib/api";
import { InfoBox, WarningBox } from "@/components/info-box";
import { Card, CardContent } from "@/components/ui/card";
import { EntryCard, categoryLabel, type Entry } from "./entry-card";
import { LeaderboardFilters } from "./filters";

export const metadata: Metadata = { title: "Leaderboard" };

type Profile = {
  key: string;
  name: string;
  description?: string | null;
  emoji?: string | null;
  category_label?: string | null;
  applicable_categories?: string[] | null;
};

type Meta = { categories: string[]; profiles: Profile[] };

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

  const profileName =
    meta.profiles.find((p) => p.key === profile)?.name ??
    "Balanced";
  const visibleProfiles = category
    ? meta.profiles.filter(
        (p) =>
          !p.applicable_categories ||
          p.applicable_categories.includes(category),
      )
    : meta.profiles;

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-10">
      <h1 className="text-3xl font-bold tracking-tight">
        🏆 Strategy Leaderboard
      </h1>
      <p className="mb-4 text-sm text-muted-foreground">
        Strategies ranked by category and investor profile
      </p>

      <InfoBox className="mb-3">
        🧠 <strong>Wisdom of the Crowd</strong>
        <p className="mt-2">
          This leaderboard is a <strong>collective intelligence engine</strong>.
          As thousands of users create and refine strategies, the top
          performers represent approaches that{" "}
          <strong>no single financial advisor would design alone</strong>.
        </p>
        <p className="mt-2">
          Research shows diverse groups outperform individual experts when
          there&apos;s a clear scoring mechanism, independent contributors, and
          effective aggregation — exactly what this leaderboard provides.
        </p>
        <p className="mt-2 text-xs">
          📖 Based on{" "}
          <a
            href="https://en.wikipedia.org/wiki/The_Wisdom_of_Crowds"
            className="underline"
            target="_blank"
            rel="noreferrer"
          >
            &ldquo;The Wisdom of Crowds&rdquo; (Surowiecki, 2004)
          </a>
        </p>
      </InfoBox>

      <WarningBox className="mb-6">
        ⚠️ <strong>Note</strong>: All strategies are evaluated using ISK
        taxation (1% annual wealth tax). Final rankings do not account for exit
        taxation that would apply under capital gains regimes.
      </WarningBox>

      <div className="mb-6">
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
        <div className="flex flex-col gap-3">
          {board.entries.map((e) => (
            <EntryCard
              key={e.id}
              entry={e}
              profile={profile}
              profileName={profileName}
            />
          ))}
        </div>
      )}

      <section className="mt-10">
        <h2 className="mb-1 text-xl font-semibold">⚖️ Weighting Profiles</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Choose a weighting profile above to see how strategies rank for
          different investor personas. Each profile emphasizes different
          performance metrics to match specific goals and risk preferences.
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          {visibleProfiles.map((p) => (
            <Card key={p.key}>
              <CardContent className="py-3 text-sm">
                <strong>
                  {p.emoji ? `${p.emoji} ` : ""}
                  {p.name}
                </strong>
                {p.description ? ` — ${p.description}` : ""}
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </main>
  );
}
