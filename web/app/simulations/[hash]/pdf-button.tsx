"use client";

import { Button } from "@/components/ui/button";
import { usePdfDownload } from "@/hooks/use-pdf-download";

export function PdfButton({ hash }: { hash: string }) {
  const { status, start } = usePdfDownload(hash);

  return (
    <Button variant="outline" onClick={start} disabled={status === "working"}>
      {status === "working"
        ? "Generating PDF…"
        : status === "error"
          ? "PDF failed — retry"
          : "📄 Download PDF"}
    </Button>
  );
}
