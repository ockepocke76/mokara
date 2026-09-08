"use client";

/**
 * Category + profile selectors. Category is the top-level frame (scores are
 * only comparable within a category); profiles cascade from it — switching
 * category resets the profile to that category's balanced variant.
 */
import { useRouter } from "next/navigation";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ProfileWeights } from "./profiles-section";
import type { CategoryOption, Profile } from "./types";

export function LeaderboardFilters({
  categories,
  profiles,
  category,
  profile,
}: {
  categories: CategoryOption[];
  profiles: Profile[];
  category: string;
  profile: string;
}) {
  const router = useRouter();
  const categoryInfo = categories.find((c) => c.key === category);
  const profileInfo = profiles.find((p) => p.key === profile);

  function setCategory(next: string) {
    // Profile intentionally dropped: the API defaults to the new category's
    // balanced variant, mirroring the old selector behavior.
    router.push(`/leaderboard?category=${encodeURIComponent(next)}`);
  }

  function setProfile(next: string) {
    router.push(
      `/leaderboard?category=${encodeURIComponent(category)}&profile=${encodeURIComponent(next)}`,
    );
  }

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div>
        <h3 className="mb-2 font-semibold">Select Strategy Type</h3>
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {categories.map((c) => (
              <SelectItem key={c.key} value={c.key}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {categoryInfo && (
          <Accordion type="single" collapsible className="mt-1">
            <AccordionItem value="about" className="border-none">
              <AccordionTrigger className="py-1.5 text-xs text-muted-foreground">
                ℹ️ About this category
              </AccordionTrigger>
              <AccordionContent className="text-sm">
                {categoryInfo.description}
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        )}
      </div>

      <div>
        <h3 className="mb-2 font-semibold">Select Investor Profile</h3>
        <Select value={profile} onValueChange={setProfile}>
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {profiles.map((p) => (
              <SelectItem key={p.key} value={p.key}>
                {p.emoji ? `${p.emoji} ` : ""}
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {profileInfo && (
          <>
            <p className="mt-1 text-xs text-muted-foreground">
              {profileInfo.description}
            </p>
            <Accordion type="single" collapsible className="mt-1">
              <AccordionItem value="weights" className="border-none">
                <AccordionTrigger className="py-1.5 text-xs text-muted-foreground">
                  📊 View Profile Weights
                </AccordionTrigger>
                <AccordionContent>
                  <ProfileWeights profile={profileInfo} showDescriptions />
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </>
        )}
      </div>
    </div>
  );
}
