export type WalkSurface = "overview" | "workbench";
export type WalkViewport = "all" | "desktop" | "mobile";
export type CardPlacement = "auto" | "top" | "bottom" | "left" | "right";

export interface WalkContext {
  displayName: string;
  subjectUrl: string | null;
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
  presentation?: "spotlight" | "welcome";
  heading: (ctx: WalkContext) => string;
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
    anchor: "syscorpus-overview-context",
    fallbackAnchor: "syscorpus-brand",
    viewport: "all",
    placement: "auto",
    presentation: "welcome",
    heading: (ctx) => `Meet ${ctx.displayName} through the lens of SysCorpus`,
    body: (ctx) => `Start with ${ctx.displayName}: what it is, how it is built, and the source evidence behind it. SysCorpus connects those layers from one recorded commit.`,
  },
  {
    id: "start-with-a-question",
    surface: "overview",
    anchor: "question-routes",
    viewport: "all",
    placement: "auto",
    heading: (ctx) => `Ask about ${ctx.displayName}`,
    body: (ctx) => `Choose what you want to understand about ${ctx.displayName}. SysCorpus assembles an answer from mapped evidence${ctx.hasGuidedPaths ? " and can guide you through the code" : ""}.`,
  },
  {
    id: "two-views",
    surface: "overview",
    anchor: "experience-switcher",
    viewport: "all",
    placement: "auto",
    heading: (ctx) => `Two views of ${ctx.displayName}`,
    body: (ctx) => `Overview tells the ${ctx.displayName} story. Workbench opens the full SysCorpus technical model and its code. Switch views without losing your place.`,
  },
  {
    id: "how-much-was-analyzed",
    surface: "overview",
    anchor: "overview-trust-button",
    viewport: "desktop",
    minWidth: 768,
    placement: "auto",
    heading: (ctx) => `How much of ${ctx.displayName} was analyzed?`,
    body: (ctx) => `See how much source SysCorpus analyzed for ${ctx.displayName}, what it skipped, and why. The limits stay one click away.`,
  },
  {
    id: "your-tools",
    surface: "overview",
    anchor: "theme-switcher",
    viewport: "all",
    placement: "left",
    heading: () => "Your exploration tools",
    body: (ctx) => `Search across ${ctx.displayName} with ${ctx.isMac ? "Cmd+K" : "Ctrl+K"}. Change the theme and viewer preferences here; SysCorpus keeps the underlying project view unchanged.`,
  },
  {
    id: "the-map",
    surface: "workbench",
    anchor: "graph-frame",
    viewport: "all",
    placement: "auto",
    heading: (ctx) => `Explore ${ctx.displayName}`,
    body: (ctx) => ctx.isMobile
      ? `Tap an area of ${ctx.displayName} to inspect it. Open it to go deeper; the SysCorpus model keeps the same structure.`
      : `Select an area of ${ctx.displayName} to inspect it. Open it to go deeper; the tree and SysCorpus model keep the same structure.`,
  },
  {
    id: "lenses",
    surface: "workbench",
    anchor: "lens-switcher",
    viewport: "all",
    placement: "left",
    heading: (ctx) => `${ctx.displayName} through lenses`,
    body: (ctx) => `SysCorpus lenses reorganize ${ctx.displayName} for a purpose: ${lensList(ctx.lensLabels)}${ctx.lensLabels.length > 3 ? " and more" : ""}. Your place is kept when you switch.`,
  },
  {
    id: "if-you-get-lost",
    surface: "workbench",
    anchor: "help-button",
    viewport: "desktop",
    placement: "auto",
    heading: () => "Come back anytime",
    body: (ctx) => `Help replays this ${ctx.displayName} tour and lists shortcuts. Overview returns to the project story; Workbench returns to the SysCorpus technical model.`,
  },
  {
    id: "if-you-get-lost-mobile",
    surface: "workbench",
    anchor: "help-button",
    viewport: "mobile",
    placement: "auto",
    heading: () => "Come back anytime",
    body: (ctx) => `Help replays the ${ctx.displayName} tour and explains the interface. Overview returns to the project story.`,
  },
] as const;
