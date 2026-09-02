import { useEffect, useState } from "react";
import { useArchStore } from "../store";

/**
 * Resolves CSS custom properties to concrete values for the few places that
 * cannot use var() directly.
 *
 * Almost all of the viewer's theming resolves in CSS: components write
 * Tailwind utility classes, those compile to var() references, and a theme
 * redefines the variables. React Flow's Background and MiniMap are the
 * exception. They take colors as props and write them where a var() reference
 * would not resolve, so this hook reads the computed value back out of the
 * root element and hands JS the same number CSS is using.
 *
 * Reading is deferred to an effect keyed on theme and dark mode, which is what
 * makes it correct: the class and data-theme attribute are set in an effect of
 * their own, so a read during render would return the outgoing theme's values.
 */
export function useThemeTokens<K extends string>(
  names: Record<K, string>,
): Record<K, string> {
  const theme = useArchStore((s) => s.theme);
  const darkMode = useArchStore((s) => s.darkMode);

  const [tokens, setTokens] = useState<Record<K, string>>(names);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const styles = window.getComputedStyle(document.documentElement);
    const next = {} as Record<K, string>;
    for (const key of Object.keys(names) as K[]) {
      const resolved = styles.getPropertyValue(names[key]).trim();
      // An unresolved property means the stylesheet has not landed yet (the
      // test environment, mainly). Keep the variable reference: it is the
      // honest fallback and still resolves anywhere var() is legal.
      next[key] = resolved || `var(${names[key]})`;
    }
    // Compared against the live previous value rather than the one captured in
    // this closure, and only replaced when something actually moved, so a
    // re-render is not queued on every theme-unrelated effect run.
    setTokens((prev) => {
      const same = (Object.keys(next) as K[]).every((k) => prev[k] === next[k]);
      return same ? prev : next;
    });
    // `names` is a literal declared at the call site and never changes
    // identity in a way that matters; theme and mode are what decide when a
    // re-read is needed.
  }, [theme, darkMode]);

  return tokens;
}
