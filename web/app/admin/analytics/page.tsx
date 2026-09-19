import type { Metadata } from "next";
import Link from "next/link";

import { apiFetch } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata: Metadata = { title: "Admin · Analytics" };

type Count = { count: number };
type Summary = {
  days: number;
  total_events: number;
  active_users: number;
  per_day: ({ day: string } & Count)[];
  by_type: ({ event_type: string } & Count)[];
  top_assets: ({ name: string } & Count)[];
  top_strategies: ({ name: string } & Count)[];
  logins_by_method: ({ method: string | null } & Count)[];
};

const WINDOWS = [7, 30, 90];

function Bar({ label, count, max }: { label: string; count: number; max: number }) {
  const pct = max > 0 ? Math.max((count / max) * 100, 2) : 0;
  return (
    <div className="flex items-center gap-2 text-sm">
      <div className="w-40 shrink-0 truncate text-muted-foreground">{label}</div>
      <div className="h-3 flex-1 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      <div className="w-10 shrink-0 text-right tabular-nums">{count}</div>
    </div>
  );
}

function BarList<T extends Count>({
  rows,
  label,
  empty,
}: {
  rows: T[];
  label: (r: T) => string;
  empty: string;
}) {
  if (rows.length === 0) {
    return <span className="text-sm text-muted-foreground">{empty}</span>;
  }
  const max = Math.max(...rows.map((r) => r.count));
  return (
    <div className="flex flex-col gap-2">
      {rows.map((r) => (
        <Bar key={label(r)} label={label(r)} count={r.count} max={max} />
      ))}
    </div>
  );
}

export default async function AdminAnalyticsPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const requested = Number((await searchParams).days);
  const days = WINDOWS.includes(requested) ? requested : 30;
  const res = await apiFetch(`/admin/analytics?days=${days}`);
  const s: Summary = await res.json();
  const dayMax = Math.max(1, ...s.per_day.map((d) => d.count));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3 text-sm">
        <span className="text-muted-foreground">Window:</span>
        {WINDOWS.map((w) => (
          <Link
            key={w}
            href={`/admin/analytics?days=${w}`}
            className={w === days ? "font-medium" : "text-muted-foreground hover:text-foreground"}
          >
            {w}d
          </Link>
        ))}
        <span className="ml-auto text-muted-foreground">
          AI token usage lives under{" "}
          <Link href="/admin/llm-usage" className="underline">LLM usage</Link>.
        </span>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardDescription>Events (last {days}d)</CardDescription>
            <CardTitle className="text-2xl">{s.total_events.toLocaleString()}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Active users</CardDescription>
            <CardTitle className="text-2xl">{s.active_users}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Events over time</CardTitle>
        </CardHeader>
        <CardContent>
          {s.per_day.length === 0 ? (
            <span className="text-sm text-muted-foreground">No events in this window.</span>
          ) : (
            <div className="flex h-32 items-end gap-1">
              {s.per_day.map((d) => (
                <div
                  key={d.day}
                  title={`${d.day}: ${d.count}`}
                  className="min-w-1 flex-1 rounded-t bg-primary"
                  style={{ height: `${Math.max((d.count / dayMax) * 100, 3)}%` }}
                />
              ))}
            </div>
          )}
          {s.per_day.length > 0 && (
            <div className="mt-1 flex justify-between text-xs text-muted-foreground">
              <span>{s.per_day[0].day}</span>
              <span>{s.per_day[s.per_day.length - 1].day}</span>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Event distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <BarList rows={s.by_type} label={(r) => r.event_type} empty="No events yet." />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Logins by method</CardTitle>
          </CardHeader>
          <CardContent>
            <BarList
              rows={s.logins_by_method}
              label={(r) => r.method ?? "unknown"}
              empty="No logins recorded yet."
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Top assets</CardTitle>
            <CardDescription>From simulation runs</CardDescription>
          </CardHeader>
          <CardContent>
            <BarList rows={s.top_assets} label={(r) => r.name} empty="No simulation runs yet." />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Top strategies</CardTitle>
            <CardDescription>From simulation runs</CardDescription>
          </CardHeader>
          <CardContent>
            <BarList rows={s.top_strategies} label={(r) => r.name} empty="No simulation runs yet." />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
