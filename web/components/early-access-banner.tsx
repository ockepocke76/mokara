"use client";

import { useSyncExternalStore, useCallback } from "react";

const KEY = "mokara-early-access-dismissed";

const subscribers = new Set<() => void>();

function readDismissed(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function EarlyAccessBanner() {
  const dismissed = useSyncExternalStore(
    useCallback((cb) => {
      subscribers.add(cb);
      return () => subscribers.delete(cb);
    }, []),
    readDismissed,
    () => true, // hidden during SSR to avoid hydration mismatch
  );

  const setVisible = (v: boolean) => {
    if (!v) {
      try {
        localStorage.setItem(KEY, "1");
      } catch {}
    }
    subscribers.forEach((cb) => cb());
  };

  if (dismissed) return null;

  return (
    <div className="bg-[var(--info-bg)] text-[var(--info-fg)]">
      <div className="mx-auto flex w-full max-w-6xl items-center gap-3 px-4 py-2 text-sm">
        <span className="flex-1">
          ✨ <strong>Early Access</strong>: You&apos;re among the first to use
          Mokara.AI! We&apos;re actively improving the platform. Share feedback
          at{" "}
          <a href="mailto:contact@mokara.ai" className="underline">
            contact@mokara.ai
          </a>
          .
        </span>
        <button
          aria-label="Dismiss"
          className="shrink-0 opacity-60 hover:opacity-100"
          onClick={() => {
            try {
              localStorage.setItem(KEY, "1");
            } catch {}
            setVisible(false);
          }}
        >
          ✕
        </button>
      </div>
    </div>
  );
}
