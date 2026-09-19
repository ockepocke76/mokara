import Link from "next/link";
import { notFound } from "next/navigation";

import { getViewer, assertViewerFresh } from "@/lib/api";

// Session-gated on every request; never prerendered (the build has no API
// to resolve a viewer against, and assertViewerFresh would throw).
export const dynamic = "force-dynamic";

const ADMIN_NAV = [
  { href: "/admin/users", label: "Users" },
  { href: "/admin/jobs", label: "Jobs" },
  { href: "/admin/system", label: "System" },
  { href: "/admin/llm-usage", label: "LLM usage" },
];

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const viewer = await getViewer();
  assertViewerFresh(viewer);
  if (!viewer.is_admin) notFound();

  return (
    <div className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
      <div className="mb-6 flex items-center gap-6">
        <h1 className="text-2xl font-semibold tracking-tight">Admin</h1>
        <nav className="flex gap-4 text-sm">
          {ADMIN_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-muted-foreground transition-colors hover:text-foreground"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
      {children}
    </div>
  );
}
