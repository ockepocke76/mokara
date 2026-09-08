"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  SimPreviewCard,
  type SimPreview,
} from "@/components/sim-preview-card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export type HistoryItem = {
  history_id: number;
  simulation_hash: string;
  name: string | null;
  created_at: string | null;
  status: string | null;
  strategy: string | null;
  asset: string | null;
  num_years: number | null;
  num_simulations: number | null;
  initial_investment: number | null;
  currency: string | null;
  description: string | null;
  success_rate?: number | null;
  median_final_net_worth?: number | null;
};

type PdfState = "idle" | "working" | "ready" | "error";

export function SimulationCard({ item }: { item: HistoryItem }) {
  const router = useRouter();
  const [pdf, setPdf] = useState<PdfState>("idle");
  const [deleting, setDeleting] = useState(false);
  const [preview, setPreview] = useState<SimPreview | null>(null);
  const [previewFailed, setPreviewFailed] = useState(false);

  const hash = item.simulation_hash;

  async function loadPreview() {
    if (preview || previewFailed) return;
    const res = await fetch(`/api/bff/simulations/${hash}/preview`);
    if (res.ok) setPreview(await res.json());
    else setPreviewFailed(true);
  }

  async function generatePdf() {
    setPdf("working");
    const res = await fetch(`/api/bff/simulations/${hash}/pdf`, {
      method: "POST",
    });
    if (!res.ok) {
      setPdf("error");
      return;
    }
    for (let i = 0; i < 120; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      const s = await fetch(`/api/bff/simulations/${hash}/pdf/status`);
      if (!s.ok) continue;
      const body = await s.json();
      if (body.pdf_status === "ready") {
        setPdf("ready");
        const a = document.createElement("a");
        a.href = `/api/bff/simulations/${hash}/pdf`;
        a.download = "";
        a.click();
        return;
      }
      if (body.pdf_status === "failed") {
        setPdf("error");
        return;
      }
    }
    setPdf("error");
  }

  async function remove() {
    setDeleting(true);
    const res = await fetch(`/api/bff/simulations/${hash}`, {
      method: "DELETE",
    });
    setDeleting(false);
    if (res.ok) router.refresh();
  }

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-4 py-4">
        <div className="min-w-0 flex-1">
          <Link
            href={`/simulations/${hash}`}
            className="font-medium hover:underline"
          >
            {item.name || "Untitled simulation"}
          </Link>
          <p className="truncate text-sm text-muted-foreground">
            {item.description ??
              `${item.strategy} · ${item.asset} · ${item.num_years} years`}
          </p>
          <div className="mt-1 flex flex-wrap gap-2 text-xs">
            {typeof item.success_rate === "number" && (
              <Badge variant="secondary">
                {(item.success_rate * 100).toFixed(0)}% success
              </Badge>
            )}
            {typeof item.median_final_net_worth === "number" && (
              <Badge variant="secondary">
                median{" "}
                {Math.round(item.median_final_net_worth).toLocaleString()}{" "}
                {item.currency ?? ""}
              </Badge>
            )}
            {item.created_at && (
              <span className="self-center text-muted-foreground">
                {new Date(item.created_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>

        <div className="flex shrink-0 gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href={`/simulations/${hash}`}>View</Link>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={generatePdf}
            disabled={pdf === "working"}
          >
            {pdf === "working"
              ? "Generating…"
              : pdf === "error"
                ? "PDF failed — retry"
                : "PDF"}
          </Button>
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="ghost" size="sm">
                Delete
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Delete this simulation?</DialogTitle>
                <DialogDescription>
                  &ldquo;{item.name || "Untitled simulation"}&rdquo; and its
                  results will be permanently removed.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button
                  variant="destructive"
                  onClick={remove}
                  disabled={deleting}
                >
                  {deleting ? "Deleting…" : "Delete permanently"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>

        <Accordion type="single" collapsible className="w-full basis-full">
          <AccordionItem value="preview" className="border-none">
            <AccordionTrigger
              className="rounded-md border px-3 py-1.5 text-xs"
              onClick={() => void loadPreview()}
            >
              📊 Preview
            </AccordionTrigger>
            <AccordionContent className="pt-3">
              {preview ? (
                <SimPreviewCard preview={preview} />
              ) : previewFailed ? (
                <p className="text-sm text-muted-foreground">
                  Preview unavailable — simulation results not yet generated.
                </p>
              ) : (
                <Skeleton className="h-56 w-full" />
              )}
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  );
}
