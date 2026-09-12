"use client";

/**
 * Full report renderer — web port of ui/simulation_results.py's
 * render_live_results/render_single_result. Consumes the ordered item
 * stream from GET /simulations/{hash}/report and reproduces the old
 * Streamlit report: warnings on top, table of contents, chapter-ordered
 * collapsible sections, Appendices sub-sections, per-type renderers.
 */
import { useMemo } from "react";
import type { Data, Layout } from "plotly.js";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { WarningBox } from "@/components/info-box";
import { Chart } from "@/components/chart";
import { Markdown } from "@/components/markdown";

export type ReportItem = {
  type: string;
  data: unknown;
  caption?: string | null;
  section?: string | null;
  sub_section?: string | null;
  description?: string | null;
};

const CHAPTER_ORDER = [
  "Important Disclaimer",
  "Executive Summary",
  "Methodology Overview",
  "Strategic Analysis",
  "Input Data Analysis",
  "Simulation Settings",
  "Simulation Summary",
  "Qualitative Analysis",
  "Appendices",
];

const APPENDIX_ORDER = [
  "Advanced Statistics",
  "Average Yearly Results",
  "Median Yearly Results",
  "Example Simulation Path",
  "Input Data Analysis",
  "Strategy Evaluations",
  "Glossary",
  "AI Prompt",
];

const DEFAULT_OPEN = new Set(["Executive Summary", "Simulation Summary"]);

function MetricsTable({
  metrics,
  title,
}: {
  metrics: { label: string; value: string }[];
  title?: string | null;
}) {
  return (
    <div className="my-3">
      {title && <p className="mb-1 text-sm font-semibold">{title}</p>}
      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableBody>
            {metrics.map((m, i) => (
              <TableRow key={i}>
                <TableCell className="w-1/3 align-top text-sm font-medium">
                  {m.label}
                </TableCell>
                <TableCell className="text-sm">
                  <Markdown>{String(m.value ?? "")}</Markdown>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function DataframeTable({ raw }: { raw: string }) {
  const parsed = useMemo(() => {
    try {
      return JSON.parse(raw) as {
        columns: string[];
        index: (string | number)[];
        data: unknown[][];
      };
    } catch {
      return null;
    }
  }, [raw]);
  if (!parsed) return null;

  const fmt = (v: unknown): string => {
    if (typeof v === "number")
      return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
    return String(v ?? "");
  };
  const negative = (v: unknown) =>
    (typeof v === "number" && v < 0) ||
    (typeof v === "string" && v.trim().startsWith("-"));

  return (
    <div className="my-3 max-h-96 overflow-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead />
            {parsed.columns.map((c) => (
              <TableHead key={c} className="whitespace-nowrap text-right">
                {c}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {parsed.index.map((idx, r) => (
            <TableRow key={r}>
              <TableCell className="font-medium">{String(idx)}</TableCell>
              {parsed.data[r]?.map((v, c) => (
                <TableCell
                  key={c}
                  className={`whitespace-nowrap text-right tabular-nums ${negative(v) ? "text-destructive" : ""}`}
                >
                  {fmt(v)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function PlotlyItem({ item }: { item: ReportItem }) {
  const fig = item.data as { data: Data[]; layout: Partial<Layout> };
  if (!fig?.data) return null;
  const height =
    typeof fig.layout?.height === "number" ? fig.layout.height : 450;
  return (
    <div className="my-3">
      {item.caption && (
        <p className="mb-1 text-sm font-semibold">{item.caption}</p>
      )}
      <Chart
        className="w-full"
        data={fig.data}
        layout={{ ...fig.layout, autosize: true, width: undefined, height }}
        config={{ displayModeBar: false, responsive: true }}
      />
      {item.description && (
        <p className="mt-1 text-sm italic text-muted-foreground">
          {item.description}
        </p>
      )}
    </div>
  );
}

function AdvancedStats({
  data,
}: {
  data: {
    name: string;
    value_str?: string;
    definition?: string;
    sim_context?: string;
    real_world?: string;
  }[];
}) {
  return (
    <Accordion type="multiple" className="my-2">
      {data.map((m, i) => (
        <AccordionItem key={i} value={`m-${i}`}>
          <AccordionTrigger className="py-2 text-sm">
            <span className="flex w-full items-center justify-between pr-3">
              <span>{m.name}</span>
              <span className="font-mono">{m.value_str ?? ""}</span>
            </span>
          </AccordionTrigger>
          <AccordionContent className="space-y-2 text-sm">
            {m.definition && (
              <div>
                <strong>Definition:</strong> <Markdown>{m.definition}</Markdown>
              </div>
            )}
            {m.sim_context && (
              <div>
                <strong>In This Simulation:</strong>{" "}
                <Markdown>{m.sim_context}</Markdown>
              </div>
            )}
            {m.real_world && (
              <div>
                <strong>Real-World Context:</strong>{" "}
                <Markdown>{m.real_world}</Markdown>
              </div>
            )}
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  );
}

function Glossary({ data }: { data: Record<string, Record<string, string>> }) {
  return (
    <div className="my-2 space-y-4">
      {Object.entries(data).map(([group, terms]) => (
        <div key={group}>
          <h4 className="mb-1 text-sm font-semibold">{group}</h4>
          <Accordion type="multiple">
            {Object.entries(terms).map(([term, def]) => (
              <AccordionItem key={term} value={term}>
                <AccordionTrigger className="py-2 text-sm">
                  {term}
                </AccordionTrigger>
                <AccordionContent className="text-sm">
                  <Markdown>{def}</Markdown>
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      ))}
    </div>
  );
}

function RenderItem({ item }: { item: ReportItem }) {
  switch (item.type) {
    case "text":
      return (
        <div className="my-2">
          {item.caption && (
            <p className="text-xs text-muted-foreground">{item.caption}</p>
          )}
          <Markdown>{String(item.data ?? "")}</Markdown>
        </div>
      );
    case "image":
      return (
        <figure className="my-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={String(item.data)}
            alt={item.caption ?? "figure"}
            className="mx-auto max-w-full rounded-lg border bg-white"
          />
          {item.caption && (
            <figcaption className="mt-1 text-center text-sm text-muted-foreground">
              {item.caption}
            </figcaption>
          )}
          {item.description && (
            <p className="mt-1 text-sm italic text-muted-foreground">
              {item.description}
            </p>
          )}
        </figure>
      );
    case "plotly":
      return <PlotlyItem item={item} />;
    case "settings_table": {
      const sections = item.data as {
        title: string;
        metrics: { label: string; value: string }[];
      }[];
      return (
        <div>
          {sections
            .filter((s) => s.metrics?.length)
            .map((s) => (
              <MetricsTable key={s.title} title={s.title} metrics={s.metrics} />
            ))}
        </div>
      );
    }
    case "key_stats_table":
    case "key_value_table":
      return (
        <MetricsTable
          title={item.caption}
          metrics={item.data as { label: string; value: string }[]}
        />
      );
    case "advanced_stats_table":
      return <AdvancedStats data={item.data as never} />;
    case "glossary":
      return <Glossary data={item.data as never} />;
    case "dataframe":
      return (
        <div>
          {item.caption && (
            <p className="text-xs text-muted-foreground">{item.caption}</p>
          )}
          <DataframeTable raw={String(item.data)} />
        </div>
      );
    case "table":
      return <DataframeTable raw={JSON.stringify(item.data)} />;
    case "error":
      return <WarningBox>❌ {String(item.data)}</WarningBox>;
    default:
      return null;
  }
}

export function ReportView({ items }: { items: ReportItem[] }) {
  const { warnings, sections } = useMemo(() => {
    const warnings: ReportItem[] = [];
    const bySection = new Map<string, ReportItem[]>();
    for (const item of items) {
      if (item.type === "warning") {
        warnings.push(item);
        continue;
      }
      if (item.section === "Log") continue;
      const section = item.section ?? "Results";
      if (!bySection.has(section)) bySection.set(section, []);
      bySection.get(section)!.push(item);
    }
    const ordered = [
      ...CHAPTER_ORDER.filter((s) => bySection.has(s)),
      ...[...bySection.keys()].filter((s) => !CHAPTER_ORDER.includes(s)),
    ];
    return {
      warnings,
      sections: ordered.map((name) => ({
        name,
        items: bySection.get(name)!,
      })),
    };
  }, [items]);

  return (
    <div className="flex flex-col gap-3">
      {warnings.map((w, i) => {
        const data = w.data as { title?: string; body?: string };
        return (
          <WarningBox key={i}>
            ⚠️ <strong>{data.title ?? "Warning"}</strong>{" "}
            {data.body ?? String(w.data)}
          </WarningBox>
        );
      })}

      <Accordion
        type="multiple"
        defaultValue={sections
          .filter((s) => DEFAULT_OPEN.has(s.name))
          .map((s) => s.name)}
        className="flex flex-col gap-2"
      >
        {sections.map((section) => (
          <AccordionItem
            key={section.name}
            value={section.name}
            className="rounded-lg border bg-card px-4"
          >
            <AccordionTrigger className="text-base font-semibold">
              {section.name}
            </AccordionTrigger>
            <AccordionContent>
              <SectionBody section={section} />
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  );
}

function SectionBody({
  section,
}: {
  section: { name: string; items: ReportItem[] };
}) {
  const intro = section.items.find((i) => i.type === "intro");
  const rest = section.items.filter((i) => i.type !== "intro");
  const hasSubs = rest.some((i) => i.sub_section);

  if (!hasSubs) {
    return (
      <div>
        {intro && (
          <p className="mb-3 border-b pb-3 text-sm italic text-muted-foreground">
            {String(intro.data)}
          </p>
        )}
        {rest.map((item, i) => (
          <RenderItem key={i} item={item} />
        ))}
      </div>
    );
  }

  const subs = new Map<string, ReportItem[]>();
  for (const item of rest) {
    const name = item.sub_section ?? "General";
    if (!subs.has(name)) subs.set(name, []);
    subs.get(name)!.push(item);
  }
  const ordered = [
    ...APPENDIX_ORDER.filter((s) => subs.has(s)),
    ...[...subs.keys()].filter((s) => !APPENDIX_ORDER.includes(s)),
  ];

  return (
    <div>
      {intro && (
        <p className="mb-3 border-b pb-3 text-sm italic text-muted-foreground">
          {String(intro.data)}
        </p>
      )}
      <Accordion type="multiple" className="flex flex-col gap-1">
        {ordered.map((name) => (
          <AccordionItem key={name} value={name}>
            <AccordionTrigger className="py-2 text-sm font-medium">
              {name}
            </AccordionTrigger>
            <AccordionContent>
              {subs.get(name)!.map((item, i) => (
                <RenderItem key={i} item={item} />
              ))}
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  );
}
