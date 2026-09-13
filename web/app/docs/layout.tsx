import { DocsMobileNav, DocsSidebarNav } from "./docs-nav";

export default function DocsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <DocsMobileNav />
      <div className="mx-auto flex w-full max-w-5xl flex-1 gap-10 px-4 py-6 md:py-10">
        <aside className="hidden w-44 shrink-0 md:block">
          <DocsSidebarNav />
        </aside>
        <article className="prose prose-neutral dark:prose-invert min-w-0 max-w-none flex-1">
          {children}
        </article>
      </div>
    </>
  );
}
