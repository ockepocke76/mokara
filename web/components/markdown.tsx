"use client";

import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";

// Engine report content embeds presentational HTML (<b>, <i>, <u>, <br/>);
// user/AI-authored strategy descriptions flow through here too, so raw HTML
// must be sanitized — scripts, iframes, event handlers, and style are
// stripped, keeping only the tags the engine legitimately emits.
const schema = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), "u"],
};

/** Shared markdown renderer: GFM tables + sanitized raw HTML. */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="prose prose-sm prose-neutral dark:prose-invert max-w-none">
      <ReactMarkdown
        rehypePlugins={[rehypeRaw, [rehypeSanitize, schema]]}
        remarkPlugins={[remarkGfm]}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
