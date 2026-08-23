import type { MouseEvent, ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

import type { HostCapabilities } from "../contracts/host-capabilities.ts";
import {
  classifyImageSource,
  classifyLinkTarget,
  SAFE_MARKDOWN_STRIP_TAGS,
  SAFE_MARKDOWN_TAGS,
} from "./safe-render-policy.ts";

const schema = {
  ...defaultSchema,
  tagNames: [...SAFE_MARKDOWN_TAGS],
  strip: [...(defaultSchema.strip ?? []), ...SAFE_MARKDOWN_STRIP_TAGS],
  attributes: {
    ...defaultSchema.attributes,
    code: [["className", /^language-./, "math-inline", "math-display"]],
    img: ["src", "alt", "title"],
    a: ["href", "title"],
  },
  protocols: {
    ...defaultSchema.protocols,
    href: ["http", "https", "mailto", "artifact"],
    src: ["data", "blob"],
  },
};

export interface SafeMarkdownProps {
  children: string;
  host: HostCapabilities;
  className?: string;
}

function textFromChildren(children: ReactNode): string {
  if (typeof children === "string" || typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(textFromChildren).join("");
  return "link";
}

export function SafeMarkdown({ children, host, className }: SafeMarkdownProps) {
  const components: Components = {
    a({ href, children: label, ...props }) {
      delete props.node;
      const target = classifyLinkTarget(href);
      if (target.kind === "blocked") return <span>{label}</span>;

      const open = async (event: MouseEvent<HTMLButtonElement>) => {
        event.preventDefault();
        if (target.kind === "external") {
          await host.navigation.openExternal(target.url);
          return;
        }
        await host.artifacts.open({
          artifactId: target.artifactId,
          title: textFromChildren(label),
          kind: "agent-artifact",
        });
      };
      return (
        <button type="button" className="nta-markdown-link" onClick={open} title={props.title}>
          {label}
        </button>
      );
    },
    img({ src, alt, ...props }) {
      delete props.node;
      const source = classifyImageSource(typeof src === "string" ? src : undefined);
      if (source.kind === "blocked") {
        return <span className="nta-blocked-image" role="img" aria-label={alt ?? "image"}>[{alt || "image"}]</span>;
      }
      return <img src={source.source} alt={alt ?? ""} loading="lazy" />;
    },
    pre({ children: content }) {
      return <pre className="nta-code-block">{content}</pre>;
    },
    table({ children: content }) {
      return <div className="nta-table-wrap"><table>{content}</table></div>;
    },
  };

  return (
    <div className={["nta-markdown", className].filter(Boolean).join(" ")}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeRaw, [rehypeSanitize, schema], [rehypeKatex, { throwOnError: false, strict: false }]]}
        components={components}
        urlTransform={(url) => url}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
