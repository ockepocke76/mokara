import type { Metadata } from "next";
import Link from "next/link";

import { apiFetch, getViewer } from "@/lib/api";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { InfoBox, WarningBox } from "@/components/info-box";
import { Markdown } from "@/components/markdown";
import { LeaderboardFilters } from "./filters";
import { EntryList } from "./entry-list";
import { ScenarioHeatmap } from "./heatmap";
import { WeightingProfilesSection } from "./profiles-section";
import type { Board, LeaderboardMeta } from "./types";

export const metadata: Metadata = { title: "Leaderboard" };

export default async function LeaderboardPage({
  searchParams,
}: {
  searchParams: Promise<{ category?: string; profile?: string }>;
}) {
  const params = await searchParams;

  const [viewer, metaRes] = await Promise.all([
    getViewer(),
    apiFetch("/leaderboard/meta"),
  ]);
  const meta: LeaderboardMeta = await metaRes.json();

  const category = meta.categories.some((c) => c.key === params.category)
    ? params.category!
    : meta.default_category;

  const qs = new URLSearchParams({ category });
  if (params.profile) qs.set("profile", params.profile);
  const boardRes = await apiFetch(`/leaderboard?${qs}`);
  const board: Board = await boardRes.json();

  const profiles = meta.profiles_by_category[category] ?? [];
  const categoryInfo = meta.categories.find((c) => c.key === category)!;
  const evalInfo = meta.evaluation_info[category];

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
          📚 Based on{" "}
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

      <LeaderboardFilters
        categories={meta.categories}
        profiles={profiles}
        category={category}
        profile={board.profile}
      />

      <div className="my-4">
        <p className="text-sm text-muted-foreground">📊 Total Strategies</p>
        <p className="text-3xl font-bold tabular-nums">{board.total}</p>
      </div>

      <hr className="mb-4" />
      <h2 className="mb-3 text-xl font-semibold">🏆 Rankings</h2>

      {!board.profile_is_balanced && (
        <InfoBox className="mb-3">
          📊 Rankings calculated with <strong>{board.profile_name}</strong>{" "}
          weights
        </InfoBox>
      )}

      {board.entries.length === 0 ? (
        <InfoBox>No strategies have been evaluated yet. Check back soon!</InfoBox>
      ) : (
        <EntryList
          entries={board.entries}
          category={category}
          profile={board.profile}
          profileName={board.profile_name}
          loggedIn={viewer.authenticated}
        />
      )}

      <hr className="my-8" />
      <WeightingProfilesSection
        profiles={profiles}
        categoryLabel={categoryInfo.label}
      />

      <hr className="my-8" />
      <Accordion type="single" collapsible>
        <AccordionItem value="heatmap" className="rounded-lg border bg-card px-4">
          <AccordionTrigger className="text-base font-semibold">
            🎯 Scenario Performance Heatmap
          </AccordionTrigger>
          <AccordionContent>
            <ScenarioHeatmap entries={board.entries} />
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      {evalInfo && (
        <>
          <hr className="my-8" />
          <Accordion type="single" collapsible>
            <AccordionItem value="how" className="rounded-lg border bg-card px-4">
              <AccordionTrigger className="text-base font-semibold">
                ℹ️ How Evaluation Works ({categoryInfo.label})
              </AccordionTrigger>
              <AccordionContent>
                <h3 className="mb-1 font-semibold">Evaluation Process</h3>
                <p className="mb-2 text-sm">
                  Strategies on the leaderboard are stress-tested across{" "}
                  <strong>8 standardized market scenarios</strong> to evaluate
                  robustness and performance.
                </p>
                <Markdown>{evalInfo.settings_markdown}</Markdown>
                <h3 className="mb-1 mt-4 font-semibold">Market Scenarios</h3>
                <Markdown>{evalInfo.scenarios_markdown}</Markdown>
                <h3 className="mb-1 mt-4 font-semibold">Score Components</h3>
                <Markdown>{evalInfo.score_components_markdown}</Markdown>
                <h3 className="mb-1 mt-4 font-semibold">
                  🧠 Wisdom of the Crowd
                </h3>
                <Markdown>{evalInfo.wisdom_markdown}</Markdown>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </>
      )}

      <hr className="my-8" />
      <section>
        <h2 className="mb-3 text-xl font-semibold">🚀 Try These Strategies</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <Button asChild variant="secondary">
            <Link href="/simulate">🚀 Run a Simulation</Link>
          </Button>
          <Button asChild variant="secondary">
            <Link href="/strategies">🎨 Design Custom Strategy</Link>
          </Button>
        </div>
      </section>
    </main>
  );
}
