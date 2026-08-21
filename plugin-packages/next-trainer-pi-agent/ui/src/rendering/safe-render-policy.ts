export type SafeLinkTarget =
  | { kind: "external"; url: string }
  | { kind: "artifact"; artifactId: string }
  | { kind: "blocked" };

export type SafeImageSource =
  | { kind: "inline"; source: string }
  | { kind: "blocked" };

const ARTIFACT_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SAFE_IMAGE_DATA = /^data:image\/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=\s]+$/i;

export function classifyLinkTarget(value: string | undefined): SafeLinkTarget {
  const input = value?.trim();
  if (!input) return { kind: "blocked" };
  if (input.startsWith("artifact:")) {
    const artifactId = input.slice("artifact:".length);
    return ARTIFACT_ID.test(artifactId)
      ? { kind: "artifact", artifactId }
      : { kind: "blocked" };
  }

  try {
    const parsed = new URL(input);
    if (parsed.protocol === "https:" || parsed.protocol === "http:" || parsed.protocol === "mailto:") {
      return { kind: "external", url: parsed.href };
    }
  } catch {
    // Relative and malformed references have no authority in the plugin frame.
  }
  return { kind: "blocked" };
}

export function classifyImageSource(value: string | undefined): SafeImageSource {
  const input = value?.trim();
  if (!input) return { kind: "blocked" };
  if (input.startsWith("blob:")) return { kind: "inline", source: input };
  if (SAFE_IMAGE_DATA.test(input)) return { kind: "inline", source: input };
  return { kind: "blocked" };
}

export const SAFE_MARKDOWN_TAGS = [
  "p", "br", "strong", "em", "del", "blockquote", "ul", "ol", "li",
  "pre", "code", "hr", "table", "thead", "tbody", "tr", "th", "td",
  "h1", "h2", "h3", "h4", "h5", "h6", "a", "img", "span", "div",
] as const;

export const SAFE_MARKDOWN_STRIP_TAGS = [
  "script", "iframe", "object", "embed", "style", "form", "input", "button",
  "textarea", "select", "option", "base", "meta", "link",
] as const;
