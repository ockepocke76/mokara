import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { apiFetch, getViewer } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Card, CardContent } from "@/components/ui/card";
import { InfoBox, WarningBox } from "@/components/info-box";
import {
  FeaturedStrategyCard,
  type FeaturedStrategy,
} from "@/components/featured-strategy-card";
import { SimPreviewCard, type SimPreview } from "@/components/sim-preview-card";
import { HomeSections, type HomePayload } from "./home-sections";

export const metadata: Metadata = { title: "Home" };

type HomeData = HomePayload & {
  featured_strategies: FeaturedStrategy[];
  recent_simulations: { simulation_hash: string; name: string }[];
};

async function fetchPreviews(
  sims: { simulation_hash: string; name: string }[],
): Promise<{ name: string; preview: SimPreview }[]> {
  const results = await Promise.all(
    sims.map(async (s) => {
      try {
        const res = await apiFetch(
          `/simulations/${encodeURIComponent(s.simulation_hash)}/preview`,
        );
        if (!res.ok) return null;
        return { name: s.name, preview: (await res.json()) as SimPreview };
      } catch {
        return null;
      }
    }),
  );
  return results.filter((r): r is { name: string; preview: SimPreview } => !!r);
}

export default async function DashboardPage() {
  const [viewer, homeRes] = await Promise.all([getViewer(), apiFetch("/home")]);
  const home: HomeData = await homeRes.json();
  const previews = await fetchPreviews(home.recent_simulations);

  if (!viewer.authenticated) {
    return (
      <GuestHome home={home} previews={previews} />
    );
  }

  const statsRes = await apiFetch("/me/stats");
  const stats = statsRes.ok
    ? ((await statsRes.json()) as { simulations: number; strategies: number })
    : { simulations: 0, strategies: 0 };

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8">
      <h1 className="mb-4 text-3xl font-bold tracking-tight">
        Welcome back, {viewer.name ?? "there"} 👋
      </h1>

      <div className="mb-6 grid grid-cols-2 gap-6 sm:max-w-md">
        <Stat label="Simulations Run" value={stats.simulations} />
        <Stat label="Strategies Created" value={stats.strategies} />
      </div>

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold">Quick Actions</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <Button asChild size="lg">
            <Link href="/simulate">🚀 Run New Simulation</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/strategies">✨ Design Strategy</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/leaderboard">🏆 View Leaderboard</Link>
          </Button>
        </div>
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold">Recent simulations</h2>
        {previews.length === 0 ? (
          <div className="flex flex-col items-start gap-3">
            <InfoBox>You haven&apos;t run any simulations yet.</InfoBox>
            <Button asChild>
              <Link href="/simulate">🚀 Start Your First Simulation</Link>
            </Button>
          </div>
        ) : (
          <>
            <div className="grid gap-4 lg:grid-cols-2">
              {previews.map(({ name, preview }) => (
                <Card key={preview.simulation_hash}>
                  <CardContent className="py-4">
                    <Link
                      href={`/simulations/${preview.simulation_hash}`}
                      className="font-semibold hover:underline"
                    >
                      {name}
                    </Link>
                    <div className="mt-2">
                      <SimPreviewCard preview={preview} />
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
            <Button asChild variant="outline" size="sm" className="mt-3">
              <Link href="/simulations">📂 View All Simulations</Link>
            </Button>
          </>
        )}
      </section>

      {home.featured_strategies.length > 0 && (
        <section className="mb-8 border-t pt-8">
          <h2 className="mb-3 text-lg font-semibold">
            🏆 Featured Strategies from the Community
          </h2>
          <div className="grid gap-4 lg:grid-cols-2">
            {home.featured_strategies.map((s) => (
              <FeaturedStrategyCard key={s.id} s={s} />
            ))}
          </div>
          <FeaturedNav />
        </section>
      )}

      <section className="border-t pt-8">
        <Accordion type="multiple">
          <AccordionItem value="kb" className="rounded-lg border bg-card px-4">
            <AccordionTrigger className="text-base font-semibold">
              📚 Knowledge Base
            </AccordionTrigger>
            <AccordionContent>
              <HomeSections payload={home} defaultOpen={false} />
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </section>
    </main>
  );
}

function GuestHome({
  home,
  previews,
}: {
  home: HomeData;
  previews: { name: string; preview: SimPreview }[];
}) {
  const spotsLeft = Math.max(0, home.beta.max_users - home.beta.current_users);

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8">
      {/* Hero (old guest landing) */}
      <div className="mb-2 flex items-center gap-3">
        <Image
          src="/mokara-mark.jpg"
          alt="Mokara"
          width={56}
          height={56}
          className="rounded-lg"
          priority
        />
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Design Better Investment Strategies, Backed by Data 🎯
        </h1>
      </div>
      <p className="mb-3 text-muted-foreground">
        <strong>Don&apos;t start from scratch.</strong> Browse proven
        strategies from our community leaderboard, customize them with our
        AI-powered designer, then stress-test against thousands of market
        scenarios.
      </p>
      <div className="mb-4 flex flex-col gap-1 text-sm">
        <p>🤖 <strong>AI-Powered Smart Strategy Builder</strong> — describe your goals in plain English</p>
        <p>🏆 <strong>Community Leaderboard</strong> — see what&apos;s working for real investors</p>
        <p>🔬 <strong>Monte Carlo Testing &amp; Backtesting</strong> — know the odds before you commit</p>
      </div>

      {home.beta.is_full ? (
        <>
          <WarningBox className="mb-2">
            🚧 <strong>Early access is currently full.</strong> We are adding
            users in phases to ensure stability.
          </WarningBox>
          <InfoBox className="mb-3">
            📧 <strong>Join the Waitlist</strong>: Email us at{" "}
            <a href="mailto:contact@mokara.ai?subject=Waitlist" className="underline">
              contact@mokara.ai
            </a>{" "}
            to get notified next!
          </InfoBox>
        </>
      ) : (
        <div className="mb-3 rounded-lg bg-green-50 px-4 py-3 text-sm text-green-800 dark:bg-green-950 dark:text-green-300">
          🚀 <strong>Early Access Open</strong>: {spotsLeft} spots remaining!
        </div>
      )}

      <div className="mb-2 flex flex-wrap gap-3">
        <Button asChild>
          <Link href="/leaderboard">🏆 Browse Strategies</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/login">
            {home.beta.is_full ? "🔑 Existing User Login" : "🔑 Login"}
          </Link>
        </Button>
      </div>
      <p className="mb-8 text-sm text-muted-foreground">
        👇 <strong>Explore below</strong> or{" "}
        <strong>login to design your own strategy</strong>
      </p>

      {/* Featured strategies (social proof early) */}
      {home.featured_strategies.length > 0 && (
        <section className="mb-10 border-t pt-8">
          <h2 className="mb-3 text-lg font-semibold">
            🏆 Featured Strategies from the Community
          </h2>
          <div className="grid gap-4 lg:grid-cols-2">
            {home.featured_strategies.map((s) => (
              <FeaturedStrategyCard key={s.id} s={s} />
            ))}
          </div>
          <FeaturedNav />
        </section>
      )}

      {/* How it works */}
      <section className="mb-10">
        <h2 className="mb-3 text-lg font-semibold">🛠️ How It Works</h2>
        <div className="flex flex-col gap-2 text-sm">
          <p><strong>1️⃣ Browse</strong> — explore community strategies ranked by performance across different market conditions</p>
          <p><strong>2️⃣ Design</strong> — clone a strategy and customize it, or use our AI designer to build one from scratch in plain English</p>
          <p><strong>3️⃣ Test</strong> — run Monte Carlo simulations and backtests to see how your strategy performs across thousands of possible futures</p>
        </div>
        <Button asChild variant="outline" size="sm" className="mt-3">
          <Link href="/docs/methodology">📖 Read Full Methodology</Link>
        </Button>
      </section>

      {/* Sample simulations */}
      {previews.length > 0 && (
        <section className="mb-10">
          <h2 className="mb-1 text-lg font-semibold">
            What You Get: Sample Simulation Results
          </h2>
          <p className="mb-3 text-xs text-muted-foreground">
            Here&apos;s what you get when you test a strategy. Every simulation
            includes success rates, risk metrics, and year-by-year projections.
          </p>
          <div className="grid gap-4 lg:grid-cols-2">
            {previews.map(({ name, preview }) => (
              <Card key={preview.simulation_hash}>
                <CardContent className="py-4">
                  <p className="font-semibold">{name}</p>
                  <div className="mt-2">
                    <SimPreviewCard preview={preview} />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* Educational sections */}
      <div className="border-t pt-8">
        <HomeSections payload={home} defaultOpen />
      </div>
    </main>
  );
}

function FeaturedNav() {
  return (
    <div className="mt-3 flex flex-wrap gap-3">
      <Button asChild variant="outline" size="sm">
        <Link href="/strategies">📝 Strategies</Link>
      </Button>
      <Button asChild variant="outline" size="sm">
        <Link href="/leaderboard">🏆 Full Leaderboard</Link>
      </Button>
      <Button asChild size="sm">
        <Link href="/strategies">✨ Design New</Link>
      </Button>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-4xl font-bold tabular-nums">{value}</p>
    </div>
  );
}

