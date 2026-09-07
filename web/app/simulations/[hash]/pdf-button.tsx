"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";

export function PdfButton({ hash }: { hash: string }) {
  const [state, setState] = useState<"idle" | "working" | "error">("idle");

  async function generate() {
    setState("working");
    const res = await fetch(`/api/bff/simulations/${hash}/pdf`, {
      method: "POST",
    });
    if (!res.ok) {
      setState("error");
      return;
    }
    for (let i = 0; i < 120; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      const s = await fetch(`/api/bff/simulations/${hash}/pdf/status`);
      if (!s.ok) continue;
      const body = await s.json();
      if (body.pdf_status === "ready") {
        const a = document.createElement("a");
        a.href = `/api/bff/simulations/${hash}/pdf`;
        a.download = "";
        a.click();
        setState("idle");
        return;
      }
      if (body.pdf_status === "failed") {
        setState("error");
        return;
      }
    }
    setState("error");
  }

  return (
    <Button variant="outline" onClick={generate} disabled={state === "working"}>
      {state === "working"
        ? "Generating PDF…"
        : state === "error"
          ? "PDF failed — retry"
          : "📄 Download PDF"}
    </Button>
  );
}
