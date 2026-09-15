import { DocsMobileNav } from "./docs-nav";

export default function DocsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <DocsMobileNav />
      <div className="mx-auto w-full max-w-4xl flex-1 px-4 py-6 md:py-10">
        <article className="prose prose-neutral dark:prose-invert min-w-0 max-w-none">
          {children}
        </article>
      </div>
    </>
  );
}
