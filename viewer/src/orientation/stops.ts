export type WalkSurface = "overview" | "workbench";
export type WalkViewport = "all" | "desktop" | "mobile";
export type CardPlacement = "auto" | "top" | "bottom" | "left" | "right";

export interface WalkContext {
  displayName: string;
  identitySummary: string | null;
  lensLabels: string[];
  hasGuidedPaths: boolean;
  isMobile: boolean;
  isMac: boolean;
}

export interface WalkStop {
  id: string;
  surface: WalkSurface;
  anchor: string;
  fallbackAnchor?: string;
  viewport: WalkViewport;
  minWidth?: number;
  placement: CardPlacement;
  heading: string;
  body: (ctx: WalkContext) => string;
}

function lensList(labels: string[]): string {
  const names = labels.slice(0, 3).map((label) => label.toLocaleLowerCase());
  if (names.length === 0) return "the views available for this map";
  return names.join(", ");
}

export const WALK_STOPS: readonly WalkStop[] = [
  {
    id: "what-this-is",
    surface: "overview",
    anchor: "identity-statement",
    fallbackAnchor: "overview-title",
    viewport: "all",
    placement: "auto",
    heading: "What this is",
    body: (ctx) => `A map of ${ctx.displayName}, drawn from its source code at one recorded commit. Every statement here links to the code it came from.`,
  },
  {
    id: "start-with-a-question",
    surface: "overview",
    anchor: "question-routes",
    viewport: "all",
    placement: "auto",
    heading: "Start with a question",
    body: (ctx) => `Pick what you want to understand. The site assembles an answer from the evidence.${ctx.hasGuidedPaths ? " Some answers come with a guided walk through the code." : ""}`,
  },
  {
    id: "two-views",
    surface: "overview",
    anchor: "experience-switcher",
    viewport: "all",
    placement: "auto",
    heading: "Two views of one map",
    body: () => "Overview tells the story. Workbench is the full interactive map with the code behind it. Switch any time without losing your place.",
  },
  {
    id: "how-much-was-read",
    surface: "overview",
    anchor: "overview-trust-button",
    viewport: "desktop",
    minWidth: 768,
    placement: "auto",
    heading: "How much was read",
    body: () => "The share of the code the analysis actually read, what it skipped, and why. Honesty is always one click away.",
  },
  {
    id: "your-tools",
    surface: "overview",
    anchor: "header-tools",
    viewport: "all",
    placement: "auto",
    heading: "Search, theme, preferences",
    body: (ctx) => `Search everything with ${ctx.isMac ? "Cmd+K" : "Ctrl+K"}. Change the theme, light or dark, and viewer preferences here.`,
  },
  {
    id: "the-map",
    surface: "workbench",
    anchor: "graph-frame",
    viewport: "all",
    placement: "auto",
    heading: "The map",
    body: (ctx) => ctx.isMobile
      ? "Tap a box to read about it. Double-tap to open it. Home returns to the top."
      : "Click a box to read about it. Double-click to open it. Home returns to the top. The tree on the left lists the same things.",
  },
  {
    id: "lenses",
    surface: "workbench",
    anchor: "lens-select",
    viewport: "all",
    placement: "auto",
    heading: "Lenses",
    body: (ctx) => `Each lens redraws the map for a purpose: ${lensList(ctx.lensLabels)}${ctx.lensLabels.length > 3 ? " and more" : ""}. Your place is kept when you switch.`,
  },
  {
    id: "if-you-get-lost",
    surface: "workbench",
    anchor: "help-button",
    viewport: "desktop",
    placement: "auto",
    heading: "If you get lost",
    body: () => "The ? button replays this walk and lists the keyboard shortcuts. Overview is one click away in the header.",
  },
  {
    id: "if-you-get-lost-mobile",
    surface: "workbench",
    anchor: "more-menu",
    viewport: "mobile",
    placement: "auto",
    heading: "If you get lost",
    body: () => "Help, preferences and review mode live under this menu. Help replays this walk. Overview is one tap away.",
  },
] as const;
