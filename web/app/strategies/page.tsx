import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { InfoBox } from "@/components/info-box";

export const metadata: Metadata = { title: "Strategies" };

export default function StrategiesPage() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center gap-6 px-4 py-24 text-center">
      <Image
        src="/mokara-mark.jpg"
        alt="Mokara"
        width={72}
        height={72}
        priority
      />
      <h1 className="text-3xl font-bold tracking-tight">
        📝 Strategy Designer
      </h1>
      <InfoBox className="text-left">
        ✨ The AI strategy designer is being rebuilt as a step-by-step,
        transparent design flow — describe your goals in plain English and
        watch your strategy get designed, tested, and explained. It will land
        here soon.
      </InfoBox>
      <p className="max-w-md text-sm text-muted-foreground">
        Meanwhile, explore how existing strategies score across investor
        profiles on the leaderboard.
      </p>
      <Button asChild>
        <Link href="/leaderboard">🏆 View Leaderboard</Link>
      </Button>
    </main>
  );
}
