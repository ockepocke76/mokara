"use client";

/** Weighting-profile transparency: persona expanders with weight bars
 *  (old display_weighting_profiles_section / _display_profile_weights). */
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Markdown } from "@/components/markdown";
import type { Profile } from "./types";

export function ProfileWeights({
  profile,
  showDescriptions = false,
}: {
  profile: Profile;
  showDescriptions?: boolean;
}) {
  return (
    <div>
      {profile.detailed_description && (
        <div className="mb-3 border-b pb-3">
          <Markdown>{profile.detailed_description}</Markdown>
        </div>
      )}
      <p className="mb-2 text-sm font-semibold">Metric Weights</p>
      <div className="flex flex-col gap-2">
        {profile.weights.map((w) => (
          <div key={w.key} className="grid grid-cols-[1fr_auto] items-center gap-3">
            <div>
              <p className="text-sm font-medium">{w.name}</p>
              {showDescriptions && w.description && (
                <p className="text-xs text-muted-foreground">{w.description}</p>
              )}
              <div className="mt-1 h-2 rounded-full bg-secondary">
                <div
                  className="h-2 rounded-full bg-primary"
                  style={{ width: `${Math.min(100, w.weight * 100)}%` }}
                />
              </div>
            </div>
            <span className="text-sm font-semibold tabular-nums">
              {(w.weight * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function WeightingProfilesSection({
  profiles,
  categoryLabel,
}: {
  profiles: Profile[];
  categoryLabel: string;
}) {
  return (
    <section>
      <h2 className="mb-1 text-xl font-semibold">
        ⚖️ Weighting Profiles ({categoryLabel})
      </h2>
      <p className="mb-4 text-sm text-muted-foreground">
        Choose a weighting profile above to see how strategies rank for
        different investor personas. Each profile emphasizes different
        performance metrics to match specific retirement goals and risk
        preferences.
      </p>
      <Accordion type="multiple" className="flex flex-col gap-2">
        {profiles.map((p) => (
          <AccordionItem
            key={p.key}
            value={p.key}
            className="rounded-lg border bg-card px-4"
          >
            <AccordionTrigger className="text-sm">
              <span>
                {p.emoji ? `${p.emoji} ` : ""}
                <strong>{p.name}</strong>
                {p.description ? ` – ${p.description}` : ""}
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <ProfileWeights profile={p} />
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </section>
  );
}
