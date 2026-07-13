import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import {
  calculatePollInterval,
  getCircuitBreakerDelay,
  useLiveMonitor,
} from "../hooks/useLiveMonitor";
import { useArchStore } from "../store";
import type { LiveConfig } from "../types";

// --- Pure function tests ---

const defaultPolling: LiveConfig["polling"] = {
  default_interval_seconds: 30,
  min_interval_seconds: 15,
  idle_interval_seconds: 120,
  adaptive: true,
  pause_when_hidden: true,
};

describe("calculatePollInterval", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2025-06-01T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns min_interval when updated less than 2 minutes ago", () => {
    const updated = new Date("2025-06-01T11:59:00Z").toISOString(); // 60s ago
    expect(calculatePollInterval(updated, defaultPolling)).toBe(15_000);
  });

  it("returns default_interval when updated between 2 and 10 minutes ago", () => {
    const updated = new Date("2025-06-01T11:55:00Z").toISOString(); // 5min ago
    expect(calculatePollInterval(updated, defaultPolling)).toBe(30_000);
  });

  it("returns idle_interval when updated more than 10 minutes ago", () => {
    const updated = new Date("2025-06-01T11:40:00Z").toISOString(); // 20min ago
    expect(calculatePollInterval(updated, defaultPolling)).toBe(120_000);
  });

  it("returns default_interval when lastUpdatedAt is null", () => {
    expect(calculatePollInterval(null, defaultPolling)).toBe(30_000);
  });

  it("uses custom polling values", () => {
    const custom: LiveConfig["polling"] = {
      ...defaultPolling,
      min_interval_seconds: 5,
      default_interval_seconds: 10,
      idle_interval_seconds: 60,
    };
    const updated = new Date("2025-06-01T11:59:30Z").toISOString(); // 30s ago
    expect(calculatePollInterval(updated, custom)).toBe(5_000);
  });
});

describe("getCircuitBreakerDelay", () => {
  it("returns normal for 0 failures", () => {
    expect(getCircuitBreakerDelay(0, false)).toEqual({
      action: "normal",
      delayMs: 0,
    });
  });

  it("returns normal for 1-4 failures", () => {
    for (let i = 1; i <= 4; i++) {
      expect(getCircuitBreakerDelay(i, false)).toEqual({
        action: "normal",
        delayMs: 0,
      });
    }
  });

  it("returns pause with 60s delay at exactly 5 failures", () => {
    expect(getCircuitBreakerDelay(5, false)).toEqual({
      action: "pause",
      delayMs: 60_000,
    });
  });

  it("returns pause for more than 5 failures when not in slow-retry", () => {
    expect(getCircuitBreakerDelay(7, false)).toEqual({
      action: "pause",
      delayMs: 60_000,
    });
  });

  it("returns slow-retry with 5 minute delay when inSlowRetry is true", () => {
    expect(getCircuitBreakerDelay(10, true)).toEqual({
      action: "slow-retry",
      delayMs: 300_000,
    });
  });

  it("slow-retry takes precedence regardless of failure count", () => {
    expect(getCircuitBreakerDelay(3, true)).toEqual({
      action: "slow-retry",
      delayMs: 300_000,
    });
  });
});

// --- Integration tests with mock fetch ---

describe("useLiveMonitor integration", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2025-06-01T12:00:00Z"));

    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    // Reset visibility so a prior test that hid the tab does not leak into the
    // next one (the poll/scheduleNext hidden guards make this observable).
    Object.defineProperty(document, "hidden", { value: false, writable: true, configurable: true });

    // Clear localStorage
    localStorage.clear();

    // Reset store to default state
    useArchStore.setState({
      liveConfig: null,
      liveVersion: null,
      liveMonitorStatus: "idle",
      statusOverlay: null,
      architecture: null,
      loading: true,
      error: null,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  function makeJsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
    return {
      ok: status >= 200 && status < 300,
      status,
      headers: {
        get: (name: string) => {
          if (name.toLowerCase() === "content-type") return "application/json";
          return headers[name.toLowerCase()] || null;
        },
      },
      json: () => Promise.resolve(body),
    };
  }

  function makeErrorResponse(status = 404) {
    return {
      ok: false,
      status,
      headers: {
        get: () => null,
      },
      json: () => Promise.reject(new Error("Not JSON")),
    };
  }

  const testConfig: LiveConfig = {
    enabled: true,
    data_url: "https://example.com/data",
    backend_mode: "github",
    project_id: "test-project",
    polling: {
      default_interval_seconds: 30,
      min_interval_seconds: 15,
      idle_interval_seconds: 120,
      adaptive: true,
      pause_when_hidden: true,
    },
    features: {
      activity_log: false,
      admin_dashboard: false,
      version_history: false,
      ci_status_overlay: true,
      realtime_ci_webhooks: false,
      realtime_push: false,
    },
  };

  it("does nothing in static mode (no live-config.json)", async () => {
    fetchMock.mockResolvedValueOnce(makeErrorResponse(404));

    renderHook(() => useLiveMonitor());

    // Flush the init() async call
    await vi.advanceTimersByTimeAsync(0);

    const state = useArchStore.getState();
    expect(state.liveConfig).toBeNull();
    expect(state.liveMonitorStatus).toBe("idle");
  });

  it("initializes polling when live-config.json is found", async () => {
    // Return live-config.json
    fetchMock.mockResolvedValueOnce(makeJsonResponse(testConfig));
    // Return version.json for the first poll
    fetchMock.mockResolvedValueOnce(
      makeJsonResponse(
        { version: 1, updated_at: "2025-06-01T11:59:00Z", commit_sha: "abc123" },
        200,
        { etag: '"v1"' },
      ),
    );
    // Return manifest.json
    fetchMock.mockResolvedValueOnce(
      makeJsonResponse({
        name: "Test",
        description: "",
        repository: null,
        generated_at: "2025-06-01T12:00:00Z",
        analyzer_version: "1.0",
        root_path: "/",
        components: [],
        relationships: [],
        stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
      }),
    );
    // Return status-overlay.json
    fetchMock.mockResolvedValueOnce(
      makeJsonResponse({
        components: {},
        architecture: {},
        updated_at: "2025-06-01T12:00:00Z",
        commit_sha: "abc123",
      }),
    );

    renderHook(() => useLiveMonitor());

    // Flush init + poll
    await vi.advanceTimersByTimeAsync(100);

    const state = useArchStore.getState();
    expect(state.liveConfig).toEqual(testConfig);
    expect(state.liveVersion).toEqual({
      version: 1,
      updated_at: "2025-06-01T11:59:00Z",
      commit_sha: "abc123",
    });
  });

  it("circuit breaker activates after 5 consecutive failures", async () => {
    // Return live-config.json
    fetchMock.mockResolvedValueOnce(makeJsonResponse(testConfig));

    // All subsequent version.json fetches fail
    for (let i = 0; i < 10; i++) {
      fetchMock.mockRejectedValueOnce(new Error("Network error"));
    }

    renderHook(() => useLiveMonitor());

    // Flush init
    await vi.advanceTimersByTimeAsync(0);

    // After first poll failure (1 failure), advance through 4 more
    for (let i = 0; i < 4; i++) {
      await vi.advanceTimersByTimeAsync(30_000);
    }

    // After 5 failures total, circuit breaker should set error status
    const stateAfter5 = useArchStore.getState();
    expect(stateAfter5.liveMonitorStatus).toBe("error");
  });

  it("circuit breaker self-heals on success after slow-retry", async () => {
    // Return live-config.json
    fetchMock.mockResolvedValueOnce(makeJsonResponse(testConfig));

    // 6 polls fail: 5 to trigger circuit breaker + 1 pause retry
    for (let i = 0; i < 6; i++) {
      fetchMock.mockRejectedValueOnce(new Error("Network error"));
    }

    // Then succeed on the slow-retry poll
    fetchMock.mockResolvedValueOnce(
      makeJsonResponse(
        { version: 1, updated_at: "2025-06-01T12:00:00Z", commit_sha: "abc" },
        200,
        { etag: '"v1"' },
      ),
    );
    fetchMock.mockResolvedValueOnce(
      makeJsonResponse({
        name: "Test",
        description: "",
        repository: null,
        generated_at: "2025-06-01T12:00:00Z",
        analyzer_version: "1.0",
        root_path: "/",
        components: [],
        relationships: [],
        stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
      }),
    );
    fetchMock.mockResolvedValueOnce(
      makeJsonResponse({
        components: {},
        architecture: {},
        updated_at: "2025-06-01T12:00:00Z",
        commit_sha: "abc",
      }),
    );

    renderHook(() => useLiveMonitor());

    // Flush init + first poll failure
    await vi.advanceTimersByTimeAsync(0);

    // 4 more failures at adaptive intervals (total 5 failures)
    for (let i = 0; i < 4; i++) {
      await vi.advanceTimersByTimeAsync(30_000);
    }

    // At 5 failures: 60s pause, then retry
    await vi.advanceTimersByTimeAsync(60_000);

    // Pause retry fails (6th failure), enters slow-retry mode
    expect(useArchStore.getState().liveMonitorStatus).toBe("error");

    // Advance 5 min for slow-retry poll (which succeeds)
    await vi.advanceTimersByTimeAsync(300_000);
    await vi.advanceTimersByTimeAsync(100);

    const state = useArchStore.getState();
    expect(state.liveMonitorStatus).toBe("idle");
  });

  it("pauses polling when tab becomes hidden", async () => {
    // Return live-config.json
    fetchMock.mockResolvedValueOnce(makeJsonResponse(testConfig));
    // Return version.json (304 not modified)
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 304,
      headers: { get: () => null },
      json: () => Promise.resolve(null),
    });

    renderHook(() => useLiveMonitor());
    await vi.advanceTimersByTimeAsync(100);

    // Simulate tab becoming hidden
    Object.defineProperty(document, "hidden", { value: true, writable: true });
    document.dispatchEvent(new Event("visibilitychange"));

    const state = useArchStore.getState();
    expect(state.liveMonitorStatus).toBe("paused");
  });

  it("resumes with immediate poll after 5+ minutes hidden", async () => {
    // Return live-config.json
    fetchMock.mockResolvedValueOnce(makeJsonResponse(testConfig));
    // First poll (304)
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 304,
      headers: { get: () => null },
      json: () => Promise.resolve(null),
    });
    // Poll after visibility restore
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 304,
      headers: { get: () => null },
      json: () => Promise.resolve(null),
    });

    renderHook(() => useLiveMonitor());
    await vi.advanceTimersByTimeAsync(100);

    // Hide tab
    Object.defineProperty(document, "hidden", { value: true, writable: true });
    document.dispatchEvent(new Event("visibilitychange"));

    // Advance 6 minutes while hidden
    await vi.advanceTimersByTimeAsync(6 * 60 * 1000);

    // Show tab
    Object.defineProperty(document, "hidden", { value: false, writable: true });
    document.dispatchEvent(new Event("visibilitychange"));

    // The immediate poll should have been triggered
    await vi.advanceTimersByTimeAsync(100);

    // Verify fetch was called for the resume poll
    // live-config.json + first poll + resume poll = at least 3 fetch calls
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("does not re-arm the poll timer when an in-flight poll completes while hidden (F-VW-7)", async () => {
    fetchMock.mockResolvedValueOnce(makeJsonResponse(testConfig)); // live-config
    // The version fetch is deferred: it stays in flight while we hide the tab.
    let resolveVersion: (r: unknown) => void;
    const deferred = new Promise((res) => { resolveVersion = res; });
    fetchMock.mockReturnValueOnce(deferred);

    renderHook(() => useLiveMonitor());
    await vi.advanceTimersByTimeAsync(0); // init runs, poll starts, version fetch in flight

    const callsBefore = fetchMock.mock.calls.length; // live-config + version

    // Hide the tab while the poll is in flight.
    Object.defineProperty(document, "hidden", { value: true, writable: true, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));

    // The in-flight poll now resolves with a 304 AFTER hiding. Its scheduleNext
    // must not arm a fresh timer while hidden (pre-fix it armed unconditionally).
    resolveVersion!(makeJsonResponse(null, 304));
    await vi.advanceTimersByTimeAsync(0);

    // Advancing well past any poll interval must not trigger another fetch.
    await vi.advanceTimersByTimeAsync(5 * 60 * 1000);
    expect(fetchMock.mock.calls.length).toBe(callsBefore);
  });

  it("drops an unversioned localStorage cache instead of rendering it (F-VW-7)", async () => {
    // Old-schema cache entry: the raw Architecture with no { v, data } wrapper.
    const staleArch = {
      name: "StaleCached",
      description: "",
      repository: null,
      generated_at: "2020-01-01T00:00:00Z",
      analyzer_version: "0.1",
      root_path: "/",
      components: [],
      relationships: [],
      symbols: [],
      files: [],
      stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
    };
    localStorage.setItem("arch-live-cache-test-project", JSON.stringify(staleArch));

    fetchMock.mockResolvedValueOnce(makeJsonResponse(testConfig)); // live-config
    fetchMock.mockRejectedValue(new Error("network")); // version fetch fails, nothing else applies

    renderHook(() => useLiveMonitor());
    await vi.advanceTimersByTimeAsync(0);

    // The stale cache must NOT be applied (pre-fix it rendered instantly), and it
    // is dropped from storage so it cannot resurface.
    expect(useArchStore.getState().architecture).toBeNull();
    expect(localStorage.getItem("arch-live-cache-test-project")).toBeNull();
  });

  it("applies a version-tagged localStorage cache for instant first render (F-VW-7)", async () => {
    const cachedArch = {
      name: "CachedV1",
      description: "",
      repository: null,
      generated_at: "2025-06-01T00:00:00Z",
      analyzer_version: "1.2.0",
      root_path: "/",
      components: [],
      relationships: [],
      symbols: [],
      files: [],
      stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
    };
    localStorage.setItem("arch-live-cache-test-project", JSON.stringify({ v: 1, data: cachedArch }));

    fetchMock.mockResolvedValueOnce(makeJsonResponse(testConfig)); // live-config
    fetchMock.mockRejectedValue(new Error("network")); // version fetch fails, cache stays

    renderHook(() => useLiveMonitor());
    await vi.advanceTimersByTimeAsync(0);

    // The versioned cache is unwrapped and applied. Pre-fix parsing { v, data }
    // as the Architecture directly left name undefined.
    expect(useArchStore.getState().architecture?.name).toBe("CachedV1");
  });
});
