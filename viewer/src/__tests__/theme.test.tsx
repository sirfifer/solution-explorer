/**
 * The theme seam.
 *
 * These tests hold the two properties the seam actually depends on, both of
 * which are easy to break silently later:
 *
 *  1. Theme and appearance stay orthogonal. Every theme ships a light and a
 *     dark variant, so switching the dress must never change the time of day
 *     and vice versa.
 *  2. Every theme in the registry is reachable and round-trips through
 *     storage, because a theme that cannot be selected or does not survive a
 *     reload is not shipped.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { act, render, screen, fireEvent } from "@testing-library/react";
import { useArchStore } from "../store";
import { ThemeSwitcher } from "../components/ThemeSwitcher";
import { ORIENTATION_SHOWCASE_EVENT } from "../orientation/showcase";
import {
  THEME_LIST,
  THEME_NAMES,
  THEMES,
  isThemeName,
  resolveDefaultTheme,
} from "../utils/themes";

const THEME_KEY = "arch-theme";

beforeEach(() => {
  localStorage.clear();
  useArchStore.setState({ theme: "signal", darkMode: true });
});

describe("theme registry", () => {
  it("ships the full launch wardrobe", () => {
    // Three launch foundations plus the two material explorations retained for
    // production: Fold and Lumen.
    expect(THEME_NAMES).toContain("signal");
    expect(THEME_NAMES).toContain("ledger");
    expect(THEME_NAMES).toContain("atlas");
    expect(THEME_NAMES).toContain("fold");
    expect(THEME_NAMES).toContain("lumen");
  });

  it("gives every theme a label, a tagline, and three swatches for the chip", () => {
    for (const theme of THEME_LIST) {
      expect(theme.label).toBeTruthy();
      expect(theme.tagline).toBeTruthy();
      expect(theme.swatch).toHaveLength(3);
      // Literal hex, not a variable: the chip must show the dress you would be
      // switching into, so it cannot be painted by the dress in force.
      for (const color of theme.swatch) {
        expect(color).toMatch(/^#[0-9a-f]{6}$/i);
      }
    }
  });

  it("rejects a stored value that is not a theme", () => {
    expect(isThemeName("ledger")).toBe(true);
    expect(isThemeName("brassworks")).toBe(false);
    expect(isThemeName(null)).toBe(false);
  });

  it("supports a per-build default without changing the Signal fallback", () => {
    expect(resolveDefaultTheme("atlas")).toBe("atlas");
    expect(resolveDefaultTheme("unknown")).toBe("signal");
    expect(resolveDefaultTheme(undefined)).toBe("signal");
  });
});

describe("theme store", () => {
  it("defaults to Signal, which stays the developer default", () => {
    expect(useArchStore.getState().theme).toBe("signal");
  });

  it("persists the selected theme", () => {
    useArchStore.getState().setTheme("ledger");
    expect(useArchStore.getState().theme).toBe("ledger");
    expect(localStorage.getItem(THEME_KEY)).toBe("ledger");
  });

  it("moves to the variant each theme was drawn in", () => {
    // Signal is a control room and is conceived dark; Ledger and Atlas are
    // paper and parchment and are conceived light. Picking a paper dress and
    // staying in Signal's night is what made a theme switch look like a
    // recolour rather than a change of material.
    useArchStore.getState().setTheme("ledger");
    expect(useArchStore.getState().darkMode).toBe(false);
    useArchStore.getState().setTheme("atlas");
    expect(useArchStore.getState().darkMode).toBe(false);
    useArchStore.getState().setTheme("signal");
    expect(useArchStore.getState().darkMode).toBe(true);
  });

  it("still lets appearance be overridden after a theme is chosen, and remembers it", () => {
    // The two remain orthogonal axes. Every theme carries both variants; the
    // default is a starting point, not a constraint.
    useArchStore.getState().setTheme("atlas");
    useArchStore.getState().toggleDarkMode();
    expect(useArchStore.getState().darkMode).toBe(true);
    expect(useArchStore.getState().theme).toBe("atlas");
    expect(localStorage.getItem("arch-dark-mode")).toBe("true");
  });

  it("declares a native variant and a glow policy for every theme", () => {
    // Paper does not glow, and the hero glow is an inline box-shadow that no
    // stylesheet can reach, so the policy has to travel with the theme.
    for (const theme of THEME_LIST) {
      expect(typeof theme.defaultDark).toBe("boolean");
      expect(typeof theme.heroGlow).toBe("boolean");
    }
    expect(THEMES.signal.heroGlow).toBe(true);
    expect(THEMES.ledger.heroGlow).toBe(false);
    expect(THEMES.atlas.heroGlow).toBe(false);
    expect(THEMES.fold.heroGlow).toBe(false);
    expect(THEMES.lumen.heroGlow).toBe(true);
  });

  it("leaves the theme alone when appearance changes", () => {
    useArchStore.getState().setTheme("ledger");
    useArchStore.getState().toggleDarkMode();
    expect(useArchStore.getState().theme).toBe("ledger");
  });
});

describe("ThemeSwitcher", () => {
  function openMenu() {
    render(<ThemeSwitcher />);
    fireEvent.click(screen.getByRole("button", { name: /^Theme:/ }));
  }

  it("offers every registered theme", () => {
    openMenu();
    for (const theme of THEME_LIST) {
      expect(screen.getByRole("menuitemradio", { name: new RegExp(theme.label) })).toBeTruthy();
    }
  });

  it("selects a theme and marks it as the current one", () => {
    openMenu();
    fireEvent.click(screen.getByRole("menuitemradio", { name: /Ledger/ }));
    expect(useArchStore.getState().theme).toBe("ledger");
  });

  it("carries appearance as a control of its own", () => {
    expect(useArchStore.getState().darkMode).toBe(true);
    openMenu();
    fireEvent.click(screen.getByRole("menuitemradio", { name: /Light/ }));
    expect(useArchStore.getState().darkMode).toBe(false);
    // Choosing the variant already in force is a no-op rather than a toggle,
    // so a second click on Light does not flip to dark.
    fireEvent.click(screen.getByRole("menuitemradio", { name: /Light/ }));
    expect(useArchStore.getState().darkMode).toBe(false);
    expect(useArchStore.getState().theme).toBe("signal");
  });

  it("names the current theme and appearance for screen readers", () => {
    useArchStore.setState({ theme: "atlas", darkMode: false });
    render(<ThemeSwitcher />);
    expect(screen.getByRole("button", { name: "Theme: Atlas, light" })).toBeTruthy();
  });

  it("expands the theme choices for their orientation stop and restores them afterward", () => {
    render(<ThemeSwitcher />);
    act(() => window.dispatchEvent(new CustomEvent(ORIENTATION_SHOWCASE_EVENT, { detail: { stopId: "your-tools" } })));
    expect(screen.getByTestId("theme-menu")).toBeTruthy();
    act(() => window.dispatchEvent(new CustomEvent(ORIENTATION_SHOWCASE_EVENT, { detail: { stopId: "the-map" } })));
    expect(screen.queryByTestId("theme-menu")).toBeNull();
  });
});

describe("applying a theme to the document", () => {
  it("writes the dress and the variant onto the root as the action runs", () => {
    // Not in an effect. The canvas resolves its grid colour by reading these
    // off the root, and a child's effect commits before its parent's, so a
    // theme applied from App would land after the canvas had already read the
    // outgoing one and the ground would render a theme behind.
    useArchStore.getState().setTheme("atlas");
    expect(document.documentElement.dataset.theme).toBe("atlas");
    expect(document.documentElement.classList.contains("light")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    useArchStore.getState().toggleDarkMode();
    expect(document.documentElement.dataset.theme).toBe("atlas");
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    useArchStore.getState().setTheme("signal");
    expect(document.documentElement.dataset.theme).toBe("signal");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});

describe("canvas ground", () => {
  it("gives each theme its own canvas pattern, since a dot grid is Signal's", () => {
    expect(THEMES.signal.canvas.variant).toBe("dots");
    expect(THEMES.ledger.canvas.variant).toBe("lines");
    // Atlas draws marks rather than rules: a ruled grid and its contour arcs
    // are different geometries at the same weight and fight each other.
    expect(THEMES.atlas.canvas.variant).toBe("cross");
    expect(THEMES.lumen.canvas.variant).toBe("dots");
  });

  it("keeps every ground fine-pitched and lightly struck", () => {
    // The ground is the one surface that must never compete for attention.
    // A coarse pitch reads as a pattern to be looked at; a fine one reads as
    // the texture of the paper. Weight is the other half: what made an early
    // Atlas the first thing anyone noticed was a sparse grid of long, heavy
    // crosses, not the crosses themselves.
    //
    // Weight is lineWidth, not size. For a cross, size is the length of the
    // arms; a mark can be drawn larger and still be quiet if it is struck
    // thinly, which is the distinction that matters here.
    for (const theme of THEME_LIST) {
      expect(theme.canvas.gap).toBeLessThanOrEqual(30);
      expect(theme.canvas.lineWidth).toBeLessThanOrEqual(2);
      expect(theme.canvas.size).toBeLessThanOrEqual(6);
    }
  });
});
