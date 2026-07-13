import { useEffect, useRef } from "react";
import { useArchStore } from "../store";
import { initializeSearch } from "../utils/search";
import type { Architecture, LiveConfig, LiveVersion, StatusOverlay } from "../types";

// --- Pure functions (exported for testing) ---

/**
 * Calculate the adaptive poll interval based on how recently the data was updated.
 * Returns interval in milliseconds.
 */
export function calculatePollInterval(
  lastUpdatedAt: string | null,
  polling: LiveConfig["polling"],
): number {
  if (!lastUpdatedAt) {
    return polling.default_interval_seconds * 1000;
  }

  const ageMs = Date.now() - new Date(lastUpdatedAt).getTime();
  const twoMinutes = 2 * 60 * 1000;
  const tenMinutes = 10 * 60 * 1000;

  if (ageMs < twoMinutes) {
    return polling.min_interval_seconds * 1000;
  }
  if (ageMs < tenMinutes) {
    return polling.default_interval_seconds * 1000;
  }
  return polling.idle_interval_seconds * 1000;
}

/**
 * Determine the circuit breaker action based on failure count.
 * Returns the action to take and the delay before next retry.
 */
export function getCircuitBreakerDelay(
  consecutiveFailures: number,
  inSlowRetry: boolean,
): { action: "normal" | "pause" | "slow-retry"; delayMs: number } {
  if (inSlowRetry) {
    return { action: "slow-retry", delayMs: 300_000 }; // 5 minutes
  }
  if (consecutiveFailures >= 5) {
    return { action: "pause", delayMs: 60_000 }; // 60 seconds
  }
  return { action: "normal", delayMs: 0 };
}

// --- Helpers ---

function isJsonResponse(res: Response): boolean {
  return res.ok && (res.headers.get("content-type")?.includes("json") ?? false);
}

function getCacheKey(config: LiveConfig): string {
  const id = config.project_id || config.data_url.replace(/[^a-zA-Z0-9]/g, "-");
  return `arch-live-cache-${id}`;
}

// Bump when the cached Architecture shape changes so a stale cache written by an
// older schema is dropped instead of rendered before the fresh fetch corrects it
// (F-VW-7). The cache entry is wrapped as { v, data }.
const CACHE_SCHEMA_VERSION = 1;

interface CachedArchitecture {
  v: number;
  data: Architecture;
}

// 30 minutes in ms
const FULL_REFRESH_INTERVAL = 30 * 60 * 1000;
// 5 minutes in ms
const VISIBILITY_THRESHOLD = 5 * 60 * 1000;

// --- Hook ---

export function useLiveMonitor(): void {
  const etagRef = useRef<string | null>(null);
  const failureCountRef = useRef(0);
  const inSlowRetryRef = useRef(false);
  const hiddenSinceRef = useRef<number | null>(null);
  const lastFullRefreshRef = useRef(Date.now());
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const configRef = useRef<LiveConfig | null>(null);
  const mountedRef = useRef(true);
  // Track whether we already did the initial pause retry (to transition to slow-retry)
  const pauseRetryDoneRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;

    const store = useArchStore.getState;
    const setState = useArchStore.setState;

    function clearTimer() {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    }

    // True when polling should stand down because the tab is hidden and the
    // config asked us to pause while hidden (F-VW-7).
    function pausedForHidden(): boolean {
      const config = configRef.current;
      return !!config?.polling.pause_when_hidden && document.hidden;
    }

    function scheduleNext(delayMs: number) {
      clearTimer();
      if (!mountedRef.current) return;
      // Do not re-arm the timer while hidden: an in-flight poll that resolves
      // after the tab was hidden would otherwise schedule a wake-up behind the
      // visibility handler's back. The visibility handler resumes on show (F-VW-7).
      if (pausedForHidden()) return;
      timerRef.current = setTimeout(poll, delayMs);
    }

    function resetFailures() {
      failureCountRef.current = 0;
      inSlowRetryRef.current = false;
      pauseRetryDoneRef.current = false;
    }

    async function poll() {
      const config = configRef.current;
      if (!config || !mountedRef.current) return;
      // Do not fetch while hidden (F-VW-7). The visibility handler owns resuming
      // when the tab becomes visible again.
      if (pausedForHidden()) return;

      setState({ liveMonitorStatus: "polling" });

      // Full refresh safety net: clear ETag every 30 minutes
      if (Date.now() - lastFullRefreshRef.current > FULL_REFRESH_INTERVAL) {
        etagRef.current = null;
      }

      try {
        // Fetch version.json with optional ETag
        const headers: Record<string, string> = {};
        if (etagRef.current) {
          headers["If-None-Match"] = etagRef.current;
        }

        const versionRes = await fetch(`${config.data_url}/version.json`, { headers });

        if (!mountedRef.current) return;

        if (versionRes.status === 304) {
          // Not modified
          resetFailures();
          setState({ liveMonitorStatus: "idle" });
          const interval = calculatePollInterval(
            store().liveVersion?.updated_at ?? null,
            config.polling,
          );
          scheduleNext(interval);
          return;
        }

        if (versionRes.ok) {
          setState({ liveMonitorStatus: "updating" });

          const version: LiveVersion = await versionRes.json();
          const newEtag = versionRes.headers.get("etag");
          if (newEtag) etagRef.current = newEtag;

          setState({ liveVersion: version });

          // Fetch manifest + status-overlay in parallel
          const [manifestRes, statusRes] = await Promise.allSettled([
            fetch(`${config.data_url}/manifest.json`),
            fetch(`${config.data_url}/status-overlay.json`),
          ]);

          if (!mountedRef.current) return;

          // Process manifest
          if (manifestRes.status === "fulfilled" && isJsonResponse(manifestRes.value)) {
            const manifest = await manifestRes.value.json();
            const data: Architecture = {
              ...manifest,
              symbols: manifest.symbols || [],
              files: manifest.files || [],
            };
            // Route through setArchitecture so the split-mode detail cache is
            // invalidated on refresh (panels refetch instead of showing stale
            // symbols) and persisted annotations are re-applied (F-VW-3, F-VW-7).
            store().setArchitecture(data);
            // Rebuild the search index; detail-derived entries are preserved by
            // the search module so previously loaded symbols stay searchable.
            initializeSearch(data);

            // Cache to localStorage, tagged with the schema version.
            try {
              const entry: CachedArchitecture = { v: CACHE_SCHEMA_VERSION, data };
              localStorage.setItem(getCacheKey(config), JSON.stringify(entry));
            } catch {
              // Quota exceeded or unavailable
            }
          }

          // Process status overlay
          if (statusRes.status === "fulfilled" && isJsonResponse(statusRes.value)) {
            const overlay: StatusOverlay = await statusRes.value.json();
            store().applyStatusOverlay(overlay);
          }

          lastFullRefreshRef.current = Date.now();
          resetFailures();
          setState({ liveMonitorStatus: "idle" });

          const interval = calculatePollInterval(version.updated_at, config.polling);
          scheduleNext(interval);
          return;
        }

        // Non-ok, non-304 response: treat as error
        throw new Error(`HTTP ${versionRes.status}`);
      } catch {
        if (!mountedRef.current) return;
        handleFailure();
      }
    }

    function handleFailure() {
      const config = configRef.current;
      if (!config) return;

      failureCountRef.current++;

      const { action, delayMs } = getCircuitBreakerDelay(
        failureCountRef.current,
        inSlowRetryRef.current,
      );

      if (action === "slow-retry") {
        setState({ liveMonitorStatus: "error" });
        scheduleNext(delayMs);
      } else if (action === "pause") {
        setState({ liveMonitorStatus: "error" });
        // Pause for 60s, then retry once
        if (!pauseRetryDoneRef.current) {
          pauseRetryDoneRef.current = true;
          scheduleNext(delayMs);
        } else {
          // Pause retry was already done and failed again, enter slow-retry
          inSlowRetryRef.current = true;
          const slowDelay = getCircuitBreakerDelay(failureCountRef.current, true).delayMs;
          scheduleNext(slowDelay);
        }
      } else {
        // Normal: just use adaptive interval
        const interval = calculatePollInterval(
          store().liveVersion?.updated_at ?? null,
          config.polling,
        );
        scheduleNext(interval);
      }
    }

    function handleVisibilityChange() {
      const config = configRef.current;
      if (!config) return;

      if (document.hidden) {
        clearTimer();
        hiddenSinceRef.current = Date.now();
        // Only set paused if we were actively monitoring (not already in error)
        if (store().liveMonitorStatus !== "error") {
          setState({ liveMonitorStatus: "paused" });
        }
      } else {
        const hiddenDuration = hiddenSinceRef.current
          ? Date.now() - hiddenSinceRef.current
          : 0;
        hiddenSinceRef.current = null;

        if (hiddenDuration >= VISIBILITY_THRESHOLD) {
          // Hidden for 5+ min: immediate poll
          poll();
        } else {
          // Hidden briefly: resume with adaptive interval
          const interval = calculatePollInterval(
            store().liveVersion?.updated_at ?? null,
            config.polling,
          );
          scheduleNext(interval);
        }
      }
    }

    async function init() {
      try {
        const res = await fetch("./live-config.json");
        if (!isJsonResponse(res)) return; // Static mode
        if (!mountedRef.current) return;

        const config: LiveConfig = await res.json();
        if (!config.enabled) return;

        configRef.current = config;
        setState({ liveConfig: config });

        // Try to load cached data for instant first render
        try {
          const cacheKey = getCacheKey(config);
          const cached = localStorage.getItem(cacheKey);
          if (cached) {
            const parsed = JSON.parse(cached) as Partial<CachedArchitecture>;
            if (parsed && parsed.v === CACHE_SCHEMA_VERSION && parsed.data) {
              // Only apply cache if no architecture data is loaded yet. Route
              // through setArchitecture so precomputed connection counts and the
              // detail cache are initialized consistently (F-VW-6).
              if (!store().architecture) {
                store().setArchitecture(parsed.data);
                initializeSearch(parsed.data);
              }
            } else {
              // Stale or unversioned cache from an older schema: drop it so it
              // cannot render before the fresh fetch corrects it (F-VW-7).
              localStorage.removeItem(cacheKey);
            }
          }
        } catch {
          // Cache read failed
        }

        // Start polling
        if (config.polling.pause_when_hidden) {
          document.addEventListener("visibilitychange", handleVisibilityChange);
        }

        poll();
      } catch {
        // live-config.json fetch failed entirely (network error, etc.)
      }
    }

    init();

    return () => {
      mountedRef.current = false;
      clearTimer();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);
}
