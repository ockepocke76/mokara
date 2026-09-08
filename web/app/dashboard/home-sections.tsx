"use client";

/** The old landing_content.render_educational_sections, as one component. */
import Link from "next/link";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { InfoBox } from "@/components/info-box";
import { Markdown } from "@/components/markdown";
import { PASSIVE_INVESTING_MD } from "@/content/passive-investing";

export type HomePayload = {
  beta: {
    is_full: boolean;
    current_users: number;
    max_users: number;
  };
  community_stats: {
    total_simulations: number;
    total_strategies: number;
    total_years_simulated: number;
    top_strategies: { strategy_identifier?: string; strategy_name?: string; count: number }[];
  } | null;
  spotlights: {
    stress_scenario: {
      name: string;
      description: string;
      annual_return: number;
      annual_volatility: number;
    };
    score_metric: { name: string; description: string } | null;
    investor_profile: {
      name: string;
      emoji?: string | null;
      description?: string | null;
    };
    did_you_know: string;
    terms_of_day: { term: string; definition: string }[];
    comparison_assets: {
      name: string;
      cagr: number;
      vol: number;
      desc?: string;
    }[];
  };
  evaluation_info: {
    settings_markdown: string;
    scenarios_markdown: string;
    score_components_markdown: string;
  };
};

const SCENARIO_EMOJI: Record<string, string> = {
  "Bull Market": "🐂",
  "Bear Market": "🐻",
  "Normal Market": "📈",
  "High Volatility": "🎢",
  "Low Volatility": "💤",
  "Extreme Bull": "🚀",
  "Extreme Bear": "🩸",
  "Sideways Market": "🦀",
};

function SpotlightCard({
  emoji,
  title,
  subtitle,
  caption,
}: {
  emoji: string;
  title: string;
  subtitle?: string | null;
  caption?: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 py-4">
        <span className="text-4xl">{emoji}</span>
        <div>
          <p className="font-semibold">{title}</p>
          {subtitle && (
            <p className="text-sm italic text-muted-foreground">{subtitle}</p>
          )}
          {caption && (
            <p className="mt-1 text-xs text-muted-foreground">{caption}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function HomeSections({
  payload,
  defaultOpen,
}: {
  payload: HomePayload;
  defaultOpen: boolean;
}) {
  const { spotlights, community_stats, evaluation_info } = payload;
  const scenario = spotlights.stress_scenario;
  const [assetA, assetB] = spotlights.comparison_assets;
  const openValues = defaultOpen
    ? ["passive", "scenario-info", "showdown"]
    : [];

  return (
    <div className="flex flex-col gap-8">
      {/* 1. Passive investing education */}
      <Accordion type="multiple" defaultValue={openValues}>
        <AccordionItem value="passive" className="rounded-lg border bg-card px-4">
          <AccordionTrigger className="text-base font-semibold">
            📚 Stop Trying to Pick Stocks. Here&apos;s What Actually Matters.
          </AccordionTrigger>
          <AccordionContent>
            <Markdown>{PASSIVE_INVESTING_MD}</Markdown>
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      {/* 2. Stress test spotlight */}
      <section>
        <h2 className="mb-3 text-xl font-semibold">
          📉 Strategy Leaderboard Stress Test Spotlight
        </h2>
        <SpotlightCard
          emoji={SCENARIO_EMOJI[scenario.name] ?? "📊"}
          title={scenario.name}
          subtitle={scenario.description}
          caption={`Simulates: ${(scenario.annual_return * 100).toFixed(0) >= "0" ? "+" : ""}${(scenario.annual_return * 100).toFixed(0)}% Return, ${(scenario.annual_volatility * 100).toFixed(0)}% Volatility`}
        />
        <Accordion type="multiple" defaultValue={openValues} className="mt-2">
          <AccordionItem value="scenario-info" className="rounded-lg border bg-card px-4">
            <AccordionTrigger className="text-sm">
              ℹ️ How these scenarios evaluate strategies
            </AccordionTrigger>
            <AccordionContent>
              <h3 className="mb-1 font-semibold">Evaluation Process</h3>
              <p className="mb-2 text-sm">
                Strategies on the leaderboard are stress-tested across{" "}
                <strong>8 standardized market scenarios</strong> to evaluate
                robustness and performance.
              </p>
              <Markdown>{evaluation_info.settings_markdown}</Markdown>
              <h3 className="mb-1 mt-4 font-semibold">Market Scenarios</h3>
              <Markdown>{evaluation_info.scenarios_markdown}</Markdown>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </section>

      {/* 3. Excellence score spotlight */}
      {spotlights.score_metric && (
        <section>
          <h2 className="mb-3 text-xl font-semibold">
            🎯 Strategy Excellence Score Spotlight
          </h2>
          <SpotlightCard
            emoji="📊"
            title={spotlights.score_metric.name}
            subtitle={spotlights.score_metric.description}
          />
          <Accordion type="multiple" className="mt-2">
            <AccordionItem value="score-info" className="rounded-lg border bg-card px-4">
              <AccordionTrigger className="text-sm">
                ℹ️ How scores are calculated
              </AccordionTrigger>
              <AccordionContent>
                <h3 className="mb-1 font-semibold">Score Components</h3>
                <Markdown>
                  {evaluation_info.score_components_markdown}
                </Markdown>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </section>
      )}

      {/* 4. Investor profile spotlight */}
      <section>
        <h2 className="mb-3 text-xl font-semibold">
          ⚖️ What type of investor are you?
        </h2>
        <SpotlightCard
          emoji={spotlights.investor_profile.emoji ?? "⚖️"}
          title={spotlights.investor_profile.name}
          subtitle={spotlights.investor_profile.description}
        />
        <p className="mt-2 text-xs text-muted-foreground">
          Did you know? You can sort the <strong>Strategy Leaderboard</strong>{" "}
          by your specific investor profile to find strategies that match your
          goals.
        </p>
        <Button asChild variant="outline" size="sm" className="mt-2">
          <Link href="/leaderboard">🏆 Go to Leaderboard</Link>
        </Button>
      </section>

      {/* 5. Community pulse */}
      {community_stats && (
        <section>
          <h2 className="mb-3 text-xl font-semibold">🌐 Community Pulse</h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Pulse label="Global Simulations Run" value={community_stats.total_simulations.toLocaleString()} />
            <Pulse label="Strategies Created" value={community_stats.total_strategies.toLocaleString()} />
            <Pulse
              label="Market Years Simulated"
              value={
                community_stats.total_years_simulated < 1_000_000
                  ? community_stats.total_years_simulated.toLocaleString()
                  : `${(community_stats.total_years_simulated / 1_000_000).toFixed(1)}M`
              }
            />
            <Pulse
              label="Most Popular Strategy"
              value={
                community_stats.top_strategies[0]?.strategy_identifier ??
                community_stats.top_strategies[0]?.strategy_name ??
                "N/A"
              }
            />
          </div>
          {community_stats.top_strategies.length > 0 && (
            <Accordion
              type="multiple"
              defaultValue={["trending"]}
              className="mt-3"
            >
              <AccordionItem value="trending" className="rounded-lg border bg-card px-4">
                <AccordionTrigger className="text-sm">
                  🔥 Trending Strategies
                </AccordionTrigger>
                <AccordionContent className="text-sm">
                  {community_stats.top_strategies.map((s, i) => (
                    <p key={i}>
                      <strong>
                        {i + 1}. {s.strategy_identifier ?? s.strategy_name}
                      </strong>{" "}
                      — {s.count} runs
                    </p>
                  ))}
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          )}
        </section>
      )}

      {/* 6. Asset class showdown */}
      {assetA && assetB && (
        <Accordion type="multiple" defaultValue={openValues}>
          <AccordionItem value="showdown" className="rounded-lg border bg-card px-4">
            <AccordionTrigger className="text-base font-semibold">
              ⚔️ Asset Class Showdown
            </AccordionTrigger>
            <AccordionContent>
              <p className="mb-3 text-xs text-muted-foreground">
                Historical/Parametric Stats (Annualized)
              </p>
              <div className="grid grid-cols-[1fr_auto_1fr] items-start gap-4">
                <div>
                  <h3 className="font-semibold">{assetA.name}</h3>
                  <Pulse label="Avg Annual Return" value={`${(assetA.cagr * 100).toFixed(1)}%`} />
                  <Pulse label="Volatility" value={`${(assetA.vol * 100).toFixed(1)}%`} />
                  {assetA.desc && (
                    <p className="mt-1 text-xs text-muted-foreground">{assetA.desc}</p>
                  )}
                </div>
                <p className="self-center text-2xl font-bold">VS</p>
                <div>
                  <h3 className="font-semibold">{assetB.name}</h3>
                  <Pulse
                    label="Avg Annual Return"
                    value={`${(assetB.cagr * 100).toFixed(1)}%`}
                    delta={(assetB.cagr - assetA.cagr) * 100}
                  />
                  <Pulse
                    label="Volatility"
                    value={`${(assetB.vol * 100).toFixed(1)}%`}
                    delta={(assetB.vol - assetA.vol) * 100}
                    deltaInverse
                  />
                  {assetB.desc && (
                    <p className="mt-1 text-xs text-muted-foreground">{assetB.desc}</p>
                  )}
                </div>
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      )}

      {/* 7. Did you know */}
      <section>
        <h2 className="mb-3 text-xl font-semibold">🤔 Did You Know?</h2>
        <InfoBox>
          <strong>Fact:</strong> {spotlights.did_you_know}
        </InfoBox>
      </section>

      {/* 8. Terms of the day */}
      {spotlights.terms_of_day.length > 0 && (
        <section>
          <h2 className="mb-3 text-xl font-semibold">📖 Terms of the Day</h2>
          <div className="flex flex-col gap-2">
            {spotlights.terms_of_day.map((t) => (
              <Card key={t.term}>
                <CardContent className="py-3">
                  <p className="text-sm font-semibold">{t.term}</p>
                  <p className="text-xs text-muted-foreground">{t.definition}</p>
                </CardContent>
              </Card>
            ))}
          </div>
          <Button asChild variant="outline" size="sm" className="mt-3">
            <Link href="/docs/glossary">Browse Full Glossary</Link>
          </Button>
        </section>
      )}
    </div>
  );
}

function Pulse({
  label,
  value,
  delta,
  deltaInverse,
}: {
  label: string;
  value: string;
  delta?: number;
  deltaInverse?: boolean;
}) {
  const deltaGood = delta !== undefined && (deltaInverse ? delta < 0 : delta > 0);
  return (
    <div className="py-1 leading-tight">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-bold tabular-nums">
        {value}
        {delta !== undefined && (
          <span
            className={`ml-2 text-xs font-medium ${deltaGood ? "text-green-600" : "text-destructive"}`}
          >
            {delta >= 0 ? "+" : ""}
            {delta.toFixed(1)}%
          </span>
        )}
      </p>
    </div>
  );
}
