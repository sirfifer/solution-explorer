/**
 * The theme registry: one entry per dress the viewer can wear.
 *
 * A theme is pure CSS. The palette lives in src/themes.generated.css and the
 * character (type, radii, texture) in src/themes.css, both keyed off the
 * data-theme attribute on the root element. Nothing here influences data
 * generation, layout, or interaction, which is the constraint the theme
 * proposal puts on theming: a customer should be able to dress their own map
 * in their own brand with a stylesheet and lose nothing.
 *
 * This file exists so the store, the switcher, and the canvas all read the
 * same list. Adding a theme means adding an entry here plus its two CSS
 * blocks, and nothing else.
 */

export const THEME_NAMES = ["signal", "ledger", "atlas", "fold", "lumen"] as const;

export type ThemeName = (typeof THEME_NAMES)[number];

export interface ThemeMeta {
  name: ThemeName;
  label: string;
  /** One line, shown under the name in the switcher. */
  tagline: string;
  /**
   * Three swatches shown as the theme's chip. Deliberately literal hex values
   * rather than theme variables: the chip has to show what you would be
   * switching to, so it cannot be painted by the theme currently in force.
   */
  swatch: [string, string, string];
  /**
   * How the canvas draws its ground. React Flow needs this as a prop rather
   * than as CSS, so it is declared here with everything else about the theme.
   */
  canvas: {
    variant: "dots" | "lines" | "cross";
    gap: number;
    /** Dot radius, or the arm length of a cross. Ignored for lines. */
    size: number;
    /** Stroke weight for lines and crosses. The mark's boldness, not its tone. */
    lineWidth: number;
  };
  /**
   * The variant this theme is designed in. Light and dark remain orthogonal
   * and every theme carries both, but they are not equally the point: Signal
   * is a control room and is conceived dark, while Ledger and Atlas are paper
   * and parchment and are conceived light. Choosing a dress moves to the
   * variant it was drawn in, and the appearance control still overrides.
   */
  defaultDark: boolean;
  /**
   * Whether the map's neon hero glow belongs in this theme. It is drawn as an
   * inline box-shadow, out of CSS's reach, so the decision has to live here.
   * Paper does not glow.
   */
  heroGlow: boolean;
}

export const THEMES: Record<ThemeName, ThemeMeta> = {
  signal: {
    name: "signal",
    label: "Signal",
    tagline: "The control room",
    swatch: ["#18181b", "#22d3ee", "#a78bfa"],
    canvas: { variant: "dots", gap: 20, size: 1, lineWidth: 1 },
    defaultDark: true,
    heroGlow: true,
  },
  ledger: {
    name: "ledger",
    label: "Ledger",
    tagline: "The boardroom",
    swatch: ["#fbfaf6", "#0f766e", "#1d4ed8"],
    canvas: { variant: "lines", gap: 28, size: 1, lineWidth: 1 },
    defaultDark: false,
    heroGlow: false,
  },
  atlas: {
    name: "atlas",
    label: "Atlas",
    tagline: "The map",
    swatch: ["#f3ebd9", "#2b5b8c", "#a64d42"],
    canvas: { variant: "cross", gap: 26, size: 5, lineWidth: 1.4 },
    defaultDark: false,
    heroGlow: false,
  },
  fold: {
    name: "fold",
    label: "Fold",
    tagline: "The paper diorama",
    swatch: ["#f6efdf", "#e76f51", "#2a9d8f"],
    // Cut paper has no ruling on it. The ground is the workbench surface, so
    // it is marked only faintly, at a wide pitch, to sit under the sheets.
    canvas: { variant: "dots", gap: 30, size: 1, lineWidth: 1 },
    defaultDark: false,
    heroGlow: false,
  },
  lumen: {
    name: "lumen",
    label: "Lumen",
    tagline: "The living reef",
    swatch: ["#041521", "#4fe3c1", "#b78bff"],
    // Sparse light points at depth. The atmosphere belongs to CSS; React Flow
    // owns the one panning structural ground, as it does for every theme.
    canvas: { variant: "dots", gap: 24, size: 1.4, lineWidth: 1 },
    defaultDark: true,
    heroGlow: true,
  },
};

export const THEME_LIST: ThemeMeta[] = THEME_NAMES.map((n) => THEMES[n]);

export function isThemeName(value: unknown): value is ThemeName {
  return typeof value === "string" && (THEME_NAMES as readonly string[]).includes(value);
}

// A publication can choose its first-visit dress at build time without
// changing the viewer-wide default. A visitor's saved choice still wins in the
// store; this value is used only when no preference exists yet.
export function resolveDefaultTheme(value: unknown): ThemeName {
  return isThemeName(value) ? value : "signal";
}

export const DEFAULT_THEME = resolveDefaultTheme(import.meta.env.VITE_DEFAULT_THEME);

/**
 * Write the dress and the time of day onto the document element.
 *
 * This has to happen synchronously when the setting changes, not in a React
 * effect. Anything that resolves a theme variable by reading computed style
 * off the root, which the canvas must do because React Flow takes its colours
 * as props, runs its own effect first: child effects commit before parent
 * effects. A theme applied in App's effect is therefore applied *after* the
 * canvas has already read it, so the canvas renders one theme behind and the
 * ground keeps the previous dress's grid colour until something else forces a
 * repaint.
 *
 * Store actions run inside the event handler, before React commits anything,
 * so calling this from them puts the attribute in place ahead of every reader.
 */
export function applyThemeToDocument(theme: ThemeName, darkMode: boolean): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.classList.toggle("dark", darkMode);
  root.classList.toggle("light", !darkMode);
}
