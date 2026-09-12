import Link from "next/link";

const DOCS_NAV = [
  { href: "/docs/about", label: "About" },
  { href: "/docs/methodology", label: "Methodology" },
  { href: "/docs/assets", label: "Assets" },
  { href: "/docs/glossary", label: "Glossary" },
  { href: "/docs/strategy-api", label: "Strategy API" },
  { href: "/docs/disclaimer", label: "Disclaimer" },
];

export default function DocsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 gap-10 px-4 py-10">
      <aside className="hidden w-44 shrink-0 md:block">
        <nav className="sticky top-20 flex flex-col gap-2 text-sm">
          {DOCS_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-muted-foreground transition-colors hover:text-foreground"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <article className="prose prose-neutral dark:prose-invert min-w-0 max-w-none flex-1">
        {children}
      </article>
    </div>
  );
}
