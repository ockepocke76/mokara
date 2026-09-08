"use client";

/** Ranked entries with Load More pagination (old showed 10 at a time). */
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { EntryCard } from "./entry-card";
import type { Entry } from "./types";

const PAGE = 10;

export function EntryList({
  entries,
  category,
  profile,
  profileName,
  loggedIn,
}: {
  entries: Entry[];
  category: string;
  profile: string;
  profileName: string;
  loggedIn: boolean;
}) {
  const [visible, setVisible] = useState(PAGE);
  const remaining = entries.length - visible;

  return (
    <div className="flex flex-col gap-3">
      {entries.slice(0, visible).map((e) => (
        <EntryCard
          key={e.id}
          entry={e}
          category={category}
          profile={profile}
          profileName={profileName}
          loggedIn={loggedIn}
        />
      ))}
      {remaining > 0 && (
        <Button
          variant="secondary"
          onClick={() => setVisible((v) => v + PAGE)}
        >
          📋 Load More ({remaining} remaining)
        </Button>
      )}
    </div>
  );
}
