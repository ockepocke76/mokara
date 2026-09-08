"use client";

/** Featured strategy card with score badge + mini radar (old ui/strategy_preview_card.py). */
import type { Data, Layout } from "plotly.js";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Card, CardContent } from "@/components/ui/card";
import { Chart } from "@/components/chart";

export type FeaturedStrategy = {
  id: number;
  name: string;
  author: string;
  category: string | null;
  excellence_score: number;
  description: string;
  radar?: { data: Data[]; layout: Partial<Layout> };
};

export function FeaturedStrategyCard({ s }: { s: FeaturedStrategy }) {
  const scoreColor =
    s.excellence_score >= 80
      ? "text-green-600"
      : s.excellence_score >= 60
        ? "text-primary"
        : "text-destructive";
  const long = s.description.length > 120;
  const truncated = long ? s.description.slice(0, 117) + "…" : s.description;

  return (
    <Card>
      <CardContent className="py-4">
        <p className="font-semibold">
          ✨ {s.name}{" "}
          <span className="font-normal text-muted-foreground">
            · by {s.author}
          </span>
        </p>
        <div className="mt-2 flex gap-4">
          <div className="min-w-0 flex-1 text-sm">
            <p>{truncated}</p>
            {long && (
              <Accordion type="single" collapsible>
                <AccordionItem value="desc" className="border-none">
                  <AccordionTrigger className="py-1 text-xs">
                    📖 Read Full Description
                  </AccordionTrigger>
                  <AccordionContent className="text-sm">
                    {s.description}
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              Category:{" "}
              {(s.category ?? "Hybrid")
                .split("_")
                .map((w) => w[0] + w.slice(1).toLowerCase())
                .join(" ")}
            </p>
          </div>
          <div className="shrink-0 rounded-md border px-3 py-1.5 text-center">
            <p className="text-xs text-muted-foreground">Excellence Score</p>
            <p className={`text-xl font-bold tabular-nums ${scoreColor}`}>
              {s.excellence_score.toFixed(1)}
            </p>
          </div>
        </div>
        {s.radar && (
          <Chart
            className="mt-2 h-64"
            data={s.radar.data}
            layout={{ ...s.radar.layout, autosize: true, width: undefined }}
          />
        )}
      </CardContent>
    </Card>
  );
}
