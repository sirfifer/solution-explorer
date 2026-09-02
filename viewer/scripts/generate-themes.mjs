/**
 * Generates viewer/src/themes.generated.css, the palette half of the theme seam.
 *
 * The viewer styles itself with Tailwind utility classes written inline in
 * components (bg-zinc-900, text-emerald-400, and so on), about 2,900 call
 * sites. Tailwind v4 compiles every one of those to a CSS custom property
 * reference, so redefining the palette variables under a [data-theme]
 * selector re-dresses the whole application without touching a component.
 * That is the Zen-garden seam the theme proposal calls for.
 *
 * The rule that keeps it safe: a theme may change a color's hue and chroma,
 * never its lightness. Every generated stop reuses the exact oklch lightness
 * Tailwind ships for that stop, so every contrast relationship the viewer
 * already relies on survives the change of dress.
 *
 * Run: node scripts/generate-themes.mjs
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const TAILWIND_THEME = resolve(here, "../node_modules/tailwindcss/theme.css");
const OUT = resolve(here, "../src/themes.generated.css");

// ---------------------------------------------------------------------------
// Read Tailwind's shipped ladder so we inherit its lightness values verbatim.
// ---------------------------------------------------------------------------

const STOPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];

function readTailwindPalette() {
  const css = readFileSync(TAILWIND_THEME, "utf8");
  const re = /--color-([a-z]+)-(\d+):\s*oklch\(([\d.]+)%\s+([\d.]+)\s+([\d.]+)\)/g;
  const palette = {};
  let m;
  while ((m = re.exec(css)) !== null) {
    const [, family, stop, l, c, h] = m;
    (palette[family] ??= {})[Number(stop)] = {
      l: Number(l),
      c: Number(c),
      h: Number(h),
    };
  }
  if (!palette.blue || !palette.zinc) {
    throw new Error(`Could not parse Tailwind palette from ${TAILWIND_THEME}`);
  }
  return palette;
}

// ---------------------------------------------------------------------------
// Theme definitions.
//
// `inks` are the small set of colors a theme actually believes in. `families`
// assigns each Tailwind color family the viewer uses to one of them, which is
// what collapses eighteen generic families into a deliberate palette.
//
// `neutral` is given as a per-stop [chroma, hue] list against the zinc
// lightness ladder. It carries most of a theme's identity, so it is spelled
// out rather than derived.
// ---------------------------------------------------------------------------

const NEUTRAL_FAMILIES = ["zinc", "slate", "gray", "neutral", "stone"];

const THEMES = {
  ledger: {
    label: "Ledger",
    // Warm paper at the light end resolving to cool slate ink at the dark end,
    // the way printed stock and printing ink actually differ.
    light: {
      neutral: [
        [0.008, 92], [0.008, 92], [0.008, 86], [0.007, 78], [0.010, 248],
        [0.018, 252], [0.026, 254], [0.032, 256], [0.036, 258], [0.038, 260],
        [0.038, 262],
      ],
      white: "oklch(100% 0 0)",          // cards stay crisp white on paper
      black: "oklch(14.1% 0.038 262)",
      page: "oklch(98.2% 0.008 92)",     // paper #FBFAF6
      grid: "oklch(94.6% 0.007 88)",     // graph-paper hairline, ~#ECEAE1
      raise: "oklch(100% 0 0)",
    },
    dark: {
      neutral: [
        [0.010, 250], [0.012, 250], [0.014, 252], [0.016, 252], [0.018, 254],
        [0.022, 255], [0.026, 256], [0.028, 257], [0.030, 258], [0.032, 259],
        [0.034, 260],
      ],
      white: "oklch(96.5% 0.008 250)",
      black: "oklch(10% 0.03 260)",
      page: "oklch(16.5% 0.032 259)",
      grid: "oklch(23.5% 0.03 258)",
      raise: "oklch(22.5% 0.03 259)",
    },
    inks: {
      // teal #0F766E, blueprint #1D4ED8, critical #B91C1C, plus a muted
      // ochre so the viewer's large amber vocabulary has somewhere to land.
      teal: { c: 0.098, h: 178 },
      blueprint: { c: 0.205, h: 264 },
      critical: { c: 0.185, h: 27 },
      flag: { c: 0.125, h: 76 },
    },
    families: {
      blue: "blueprint", indigo: "blueprint", sky: "blueprint",
      violet: "blueprint", purple: "blueprint", fuchsia: "blueprint",
      emerald: "teal", green: "teal", teal: "teal", cyan: "teal", lime: "teal",
      red: "critical", rose: "critical", pink: "critical",
      amber: "flag", yellow: "flag", orange: "flag",
    },
  },

  fold: {
    label: "Fold",
    // Cut paper. Cream stock, charcoal ink, and a warm neutral that stays
    // paper rather than drifting grey, so every card reads as a sheet that
    // was cut and laid down rather than a surface that was rendered.
    light: {
      neutral: [
        [0.014, 78], [0.018, 76], [0.022, 74], [0.024, 72], [0.020, 68],
        [0.018, 66], [0.017, 64], [0.016, 62], [0.015, 60], [0.014, 58],
        [0.013, 56],
      ],
      white: "oklch(97.6% 0.012 80)",    // the cut sheet
      black: "oklch(14.1% 0.013 56)",
      page: "oklch(94.6% 0.020 76)",     // cream #F6EFDF
      grid: "oklch(91.5% 0.020 74)",
      raise: "oklch(97.6% 0.012 80)",
    },
    // Lamplit workshop: the same bench after dark, warm rather than cold.
    dark: {
      neutral: [
        [0.012, 74], [0.014, 72], [0.016, 70], [0.018, 68], [0.020, 64],
        [0.022, 62], [0.024, 60], [0.026, 58], [0.028, 56], [0.030, 54],
        [0.030, 52],
      ],
      white: "oklch(94% 0.014 74)",
      black: "oklch(9.5% 0.028 52)",
      page: "oklch(18.5% 0.028 54)",
      grid: "oklch(25% 0.028 56)",
      raise: "oklch(24% 0.03 55)",
    },
    inks: {
      // coral #E76F51, teal #2A9D8F, mustard #E9C46A, sky paper #CFE0EA.
      coral: { c: 0.145, h: 34 },
      teal: { c: 0.105, h: 178 },
      mustard: { c: 0.125, h: 82 },
      sky: { c: 0.072, h: 232 },
    },
    families: {
      blue: "sky", indigo: "sky", sky: "sky", cyan: "teal",
      violet: "coral", purple: "coral", fuchsia: "coral",
      emerald: "teal", green: "teal", teal: "teal", lime: "teal",
      red: "coral", rose: "coral", pink: "coral",
      amber: "mustard", yellow: "mustard", orange: "mustard",
    },
  },

  atlas: {
    label: "Atlas",
    light: {
      // Parchment #F3EBD9 through sepia ink #3E3120.
      neutral: [
        [0.020, 84], [0.026, 82], [0.030, 80], [0.030, 78], [0.026, 74],
        [0.026, 72], [0.026, 70], [0.026, 68], [0.026, 66], [0.024, 64],
        [0.022, 62],
      ],
      white: "oklch(96.5% 0.018 84)",    // etched landmark card
      black: "oklch(14.1% 0.022 62)",
      page: "oklch(93.5% 0.028 82)",     // parchment
      grid: "oklch(90.6% 0.026 80)",     // faint contour, ~#EBE2CD
      raise: "oklch(96.5% 0.018 84)",
    },
    dark: {
      // Night navigation: the same chart read by lamplight.
      neutral: [
        [0.016, 258], [0.020, 259], [0.024, 260], [0.028, 261], [0.032, 262],
        [0.036, 263], [0.040, 264], [0.042, 264], [0.044, 265], [0.046, 265],
        [0.048, 266],
      ],
      white: "oklch(95% 0.018 259)",
      black: "oklch(9% 0.04 266)",
      page: "oklch(17.5% 0.046 265)",
      grid: "oklch(24% 0.044 265)",
      raise: "oklch(23.5% 0.044 265)",
    },
    inks: {
      // lapis #2B5B8C, viridian #3D7A5D, madder #A64D42, ochre #C8912E.
      lapis: { c: 0.112, h: 252 },
      viridian: { c: 0.092, h: 155 },
      madder: { c: 0.122, h: 30 },
      ochre: { c: 0.122, h: 78 },
    },
    families: {
      blue: "lapis", indigo: "lapis", sky: "lapis", cyan: "lapis",
      violet: "lapis", purple: "lapis", fuchsia: "lapis",
      emerald: "viridian", green: "viridian", teal: "viridian", lime: "viridian",
      red: "madder", rose: "madder", pink: "madder",
      amber: "ochre", yellow: "ochre", orange: "ochre",
    },
  },

  lumen: {
    label: "Lumen",
    // Living light at depth. The neutral ladder stays blue-green in both
    // variants; the light version is a sunlit shallows rather than an inversion.
    light: {
      neutral: [
        [0.012, 184], [0.016, 186], [0.020, 188], [0.024, 190], [0.026, 194],
        [0.028, 198], [0.030, 202], [0.032, 206], [0.034, 210], [0.036, 214],
        [0.038, 218],
      ],
      white: "oklch(98.5% 0.012 184)",
      black: "oklch(12% 0.038 218)",
      page: "oklch(96.2% 0.020 190)",
      grid: "oklch(89.5% 0.026 194)",
      raise: "oklch(99% 0.010 184)",
    },
    dark: {
      neutral: [
        [0.018, 210], [0.022, 210], [0.026, 212], [0.030, 212], [0.034, 214],
        [0.038, 214], [0.042, 216], [0.046, 216], [0.050, 218], [0.052, 218],
        [0.054, 220],
      ],
      white: "oklch(96.8% 0.016 184)",
      black: "oklch(8.5% 0.040 220)",
      page: "oklch(14.5% 0.042 218)",
      grid: "oklch(22.5% 0.040 210)",
      raise: "oklch(19.5% 0.044 214)",
    },
    inks: {
      biolume: { c: 0.145, h: 174 },
      ray: { c: 0.110, h: 220 },
      medusa: { c: 0.145, h: 298 },
      coral: { c: 0.135, h: 32 },
    },
    families: {
      blue: "ray", indigo: "medusa", sky: "ray", cyan: "ray",
      violet: "medusa", purple: "medusa", fuchsia: "medusa",
      emerald: "biolume", green: "biolume", teal: "biolume", lime: "biolume",
      red: "coral", rose: "coral", pink: "medusa",
      amber: "coral", yellow: "coral", orange: "coral",
    },
  },
};

// ---------------------------------------------------------------------------
// Generation
// ---------------------------------------------------------------------------

/**
 * Rescale a family's chroma onto an ink while keeping the ramp's shape: a
 * stop that was a quarter as saturated as its family's 500 stays a quarter as
 * saturated as the ink. Without this, pale 50/100 tints come out as loud as
 * the 500s and every badge in the viewer shouts.
 */
function inkChromaFor(inkChroma, familyStops, stop) {
  const reference = familyStops[500]?.c || 0.2;
  const ratio = (familyStops[stop]?.c ?? 0) / reference;
  return Math.min(inkChroma * ratio, inkChroma * 1.15);
}

function fmt(n, places = 3) {
  return Number(n.toFixed(places)).toString();
}

function buildMode(theme, mode, palette) {
  const spec = theme[mode];
  const lines = [];

  // Neutrals. Every neutral family collapses onto one ramp so a theme reads as
  // one material rather than five.
  for (const family of NEUTRAL_FAMILIES) {
    STOPS.forEach((stop, i) => {
      const base = palette.zinc[stop];
      const [c, h] = spec.neutral[i];
      lines.push(`--color-${family}-${stop}: oklch(${fmt(base.l, 1)}% ${fmt(c)} ${fmt(h, 1)});`);
    });
  }

  // Accents, each family remapped onto the ink the theme assigns it.
  for (const [family, inkName] of Object.entries(theme.families)) {
    const ink = theme.inks[inkName];
    const familyStops = palette[family];
    if (!familyStops) continue;
    for (const stop of STOPS) {
      const base = familyStops[stop];
      if (!base) continue;
      const c = inkChromaFor(ink.c, familyStops, stop);
      lines.push(`--color-${family}-${stop}: oklch(${fmt(base.l, 1)}% ${fmt(c)} ${fmt(ink.h, 1)});`);
    }
  }

  lines.push(`--color-white: ${spec.white};`);
  lines.push(`--color-black: ${spec.black};`);
  lines.push(`--se-page: ${spec.page};`);
  lines.push(`--se-grid: ${spec.grid};`);
  lines.push(`--se-raise: ${spec.raise};`);

  return lines;
}

function main() {
  const palette = readTailwindPalette();
  const out = [
    "/*",
    " * GENERATED FILE. Do not edit by hand.",
    " * Source: scripts/generate-themes.mjs. Regenerate with:",
    " *   node scripts/generate-themes.mjs",
    " *",
    " * The palette half of the theme seam. Each block redefines the Tailwind",
    " * color variables that the viewer's utility classes already resolve",
    " * through, so a theme re-dresses every component without editing one.",
    " * Lightness is inherited from Tailwind unchanged; only hue and chroma",
    " * move, which is what preserves the viewer's contrast under every dress.",
    " *",
    " * The character half (type, radii, texture, chrome) is themes.css.",
    " */",
    "",
  ];

  for (const [name, theme] of Object.entries(THEMES)) {
    for (const mode of ["light", "dark"]) {
      out.push(`/* ${theme.label}, ${mode} */`);
      out.push(`html[data-theme="${name}"].${mode} {`);
      for (const line of buildMode(theme, mode, palette)) {
        out.push(`  ${line}`);
      }
      out.push("}");
      out.push("");
    }
  }

  writeFileSync(OUT, out.join("\n"));
  const count = out.filter((l) => l.trim().startsWith("--")).length;
  console.log(`Wrote ${OUT} (${count} declarations)`);
}

main();
