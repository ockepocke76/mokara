"use client";

import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";

/** Shared markdown renderer: GFM tables + raw HTML (engine content uses both). */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="prose prose-sm prose-neutral dark:prose-invert max-w-none">
      <ReactMarkdown rehypePlugins={[rehypeRaw]} remarkPlugins={[remarkGfm]}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
