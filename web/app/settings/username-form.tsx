"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function UsernameForm({ current }: { current: string }) {
  const router = useRouter();
  const [value, setValue] = useState(current);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function randomize() {
    setBusy(true);
    try {
      const res = await fetch("/api/bff/me/username");
      if (res.ok) setValue((await res.json()).username);
    } finally {
      setBusy(false);
    }
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNote(null);
    try {
      const res = await fetch("/api/bff/me/username", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: value }),
      });
      const body = await res.json();
      if (res.ok) {
        setNote({ ok: true, text: "✅ Username saved." });
        router.refresh();
      } else {
        setNote({
          ok: false,
          text: `❌ ${typeof body.detail === "string" ? body.detail : "Could not save username."}`,
        });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="flex flex-col gap-3">
      <div className="flex gap-2">
        <Input
          value={value}
          maxLength={30}
          placeholder="Enter your username"
          onChange={(e) => setValue(e.target.value)}
        />
        <Button
          type="button"
          variant="secondary"
          onClick={randomize}
          disabled={busy}
        >
          🎲 Random
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Max 30 characters. Letters, numbers, and spaces only.
      </p>
      {note && (
        <p
          className={`text-sm ${note.ok ? "text-muted-foreground" : "text-destructive"}`}
        >
          {note.text}
        </p>
      )}
      <Button
        type="submit"
        disabled={busy || value.trim() === current}
        className="self-start"
      >
        💾 Save Username
      </Button>
    </form>
  );
}
