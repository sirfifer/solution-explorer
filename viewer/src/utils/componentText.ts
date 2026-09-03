import type { Component } from "../types";

const PLACEHOLDER = /^%[^%\n]+%$/;

export function usableComponentText(value: string | null | undefined): string | null {
  const text = value?.replace(/\s+/g, " ").trim();
  if (!text || PLACEHOLDER.test(text)) return null;
  return text;
}

/**
 * Prefer repository-derived prose, then the concise enrichment summary. Help
 * text is deliberately last: it can contain broader inferred assertions and
 * should never displace a directly extracted purpose or description.
 */
export function componentSummary(component: Component): string | null {
  return usableComponentText(component.docs?.purpose)
    ?? usableComponentText(component.description)
    ?? usableComponentText(component.ai_enhance?.description)
    ?? usableComponentText(component.ai_enhance?.help_text);
}

export function componentHelp(component: Component): string | null {
  return usableComponentText(component.ai_enhance?.help_text)
    ?? componentSummary(component)
    ?? usableComponentText(component.docs?.readme)?.slice(0, 200)
    ?? null;
}
