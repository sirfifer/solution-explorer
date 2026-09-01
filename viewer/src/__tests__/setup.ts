/**
 * Test environment repair.
 *
 * Vitest 4's jsdom environment stopped exposing `localStorage` on the global
 * object, though jsdom itself still implements it. The viewer persists real
 * user state there (theme, appearance, enhanced frames, the live-monitor
 * cache), so without it a large part of the suite fails on a TypeError before
 * it reaches an assertion.
 *
 * The shim installs only when the environment has not provided the real thing,
 * so it disappears on its own the day the upstream regression is fixed rather
 * than quietly shadowing a working implementation.
 *
 * It is a faithful Storage: string coercion on both key and value, `length`
 * and `key()` in insertion order, and `null` (not undefined) for a miss. Code
 * under test should not be able to tell the difference.
 */

class MemoryStorage implements Storage {
  #entries = new Map<string, string>();

  get length(): number {
    return this.#entries.size;
  }

  clear(): void {
    this.#entries.clear();
  }

  getItem(key: string): string | null {
    const value = this.#entries.get(String(key));
    return value === undefined ? null : value;
  }

  key(index: number): string | null {
    return [...this.#entries.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.#entries.delete(String(key));
  }

  setItem(key: string, value: string): void {
    this.#entries.set(String(key), String(value));
  }

  [name: string]: unknown;
}

function install(name: "localStorage" | "sessionStorage") {
  if (typeof globalThis[name] !== "undefined") return;
  const storage = new MemoryStorage();
  Object.defineProperty(globalThis, name, {
    value: storage,
    configurable: true,
    writable: true,
  });
  if (typeof window !== "undefined" && typeof window[name] === "undefined") {
    Object.defineProperty(window, name, {
      value: storage,
      configurable: true,
      writable: true,
    });
  }
}

install("localStorage");
install("sessionStorage");
