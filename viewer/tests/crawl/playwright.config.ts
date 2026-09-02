import { defineConfig, devices } from "@playwright/test";

/**
 * The deterministic GUI crawl (design authority: README.md in this directory).
 *
 * This is the scripted counterpart to viewer/tests/gui/, not a replacement for
 * it. The AI-operated plan judges whether a surface reads correctly to a human;
 * this crawl proves, mechanically and exhaustively, that everything the data
 * says exists is reachable in the UI and renders without erroring. The two
 * answer different questions and neither subsumes the other.
 *
 * Configured by environment so one suite runs against any dataset:
 *
 *   CRAWL_SERVE_DIR   directory to serve (an assembled root from
 *                     scripts/gui-datasets.py assemble). When set, Playwright
 *                     starts the static server itself.
 *   CRAWL_BASE_URL    an already-running origin to crawl instead.
 *   CRAWL_DATA_DIR    the projection directory on disk, read to build the
 *                     expectation model. Defaults to
 *                     <CRAWL_SERVE_DIR>/architecture.
 *   CRAWL_MAX_COMPONENTS  budget for the per-component sweeps. 0 means all.
 *                     Whatever is dropped is logged by name count, never
 *                     silently.
 *   CRAWL_ALLOW_ERRORS  comma-separated URL path fragments that may 404. The
 *                     default list mirrors datasets.yaml's probe inventory for
 *                     a split-layout dataset.
 *   CRAWL_PROFILE     "quick" (the default) or "full". Quick budgets only the
 *                     exhaustive per-component sweeps; the bounded specs
 *                     (surfaces, graph, journeys, tours) always run in full.
 *   CRAWL_MOBILE      "0" disables the mobile project. It runs by default,
 *                     because a mobile failure is a real failure.
 *   CRAWL_CHANNEL     the maturity channel the expectations assume (default
 *                     stable, which is what the app resolves without ?channel=).
 */

const serveDir = process.env.CRAWL_SERVE_DIR;
const baseURL = process.env.CRAWL_BASE_URL ?? "http://127.0.0.1:4180";
const port = Number(new URL(baseURL).port || 4180);

/**
 * Profiles, and what each one actually bounds.
 *
 * The distinction the profiles encode is between the two kinds of work this
 * suite does. The EXHAUSTIVE sweeps (every component by URL, every tab of every
 * component) cost one navigation per component and are hour-scale on a large
 * subject, so they are what a budget is for. The BOUNDED specs (surfaces,
 * graph, journeys, tours) do a fixed amount of work whatever the subject's size
 * and always run in full: budgeting them would mean sometimes not playing a
 * tour, which is the thing the suite was extended to check.
 *
 * quick therefore sets CRAWL_MAX_COMPONENTS to 40 and full leaves it unset, and
 * an explicit CRAWL_MAX_COMPONENTS always wins over both, so a caller who has
 * named a budget is never overridden by a profile they did not think about.
 */
const profile = process.env.CRAWL_PROFILE ?? "quick";
if (profile === "quick" && process.env.CRAWL_MAX_COMPONENTS === undefined) {
  process.env.CRAWL_MAX_COMPONENTS = "40";
}

// The mobile project runs unless it is switched off by name. Defaulting it ON
// is the decision: a second viewport that only runs when someone remembers to
// ask for it is a viewport nobody tests.
const mobileEnabled = process.env.CRAWL_MOBILE !== "0";

export default defineConfig({
  testDir: ".",
  // The sweeps are long by construction (one navigation per component, then one
  // click per tab it offers), so the per-test timeout is generous while the
  // per-action timeout below stays tight: a slow suite is acceptable, a hung
  // assertion is not. At private large-repository validation corpus's scale (573 components, ten-ish tabs each)
  // a full unbudgeted tab sweep is an hour-scale job, which is why this is
  // measured in hours rather than minutes.
  timeout: 2 * 60 * 60 * 1000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  // One worker per PROJECT, not per file.
  //
  // The two projects are independent browsers over the same static server, and
  // the server is a file server: serving two readers is what it is for. Running
  // them in sequence doubled the wall clock for no signal, and Playwright is
  // fast enough that a slow suite means the suite is being used badly rather
  // than that the work is large.
  //
  // Still not fullyParallel: cases WITHIN a project share a page fixture and a
  // recorder, and several of them deliberately reason about what the previous
  // navigation left behind. Two workers, one per project, is the parallelism
  // that is actually available here.
  //
  // This is unrelated to the control plane's serial guard, which is about not
  // running two heavy JOBS at once, not about workers inside one run.
  workers: mobileEnabled ? 2 : 1,
  retries: 0,
  reporter: [
    ["list"],
    ["json", { outputFile: "results/crawl-results.json" }],
    // Publishes the run to the testboard as it happens, so whoever wants to
    // watch can, whether or not they are the one who started it.
    ["./testboard-reporter.ts"],
  ],
  outputDir: "results/artifacts",
  // Mirrors a remote projection to disk and sets CRAWL_DATA_DIR before any
  // worker starts. A no-op for a local serve root.
  globalSetup: "./global-setup.ts",
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"] },
    },
    // The second form factor. The detail panel lives in a bottom sheet here and
    // the lens panels in a second sheet, but the selector contract is identical
    // on both, so no spec branches on viewport: a test that needed to know
    // which viewport it was on would be testing the layout rather than the
    // behaviour.
    ...(mobileEnabled
      ? [
          {
            name: "mobile",
            use: { ...devices["iPhone 13"] },
            grep: /@mobile/,
          },
        ]
      : []),
  ],
  use: {
    baseURL,
    // Both are load bearing. Playwright's default action timeout is "wait
    // forever", so a click on an element that never becomes actionable hangs
    // the whole run with no output at all rather than failing the case. The
    // first crawl run did exactly that; a bounded action is what turns a
    // stuck UI into a reported defect.
    // The generous default, for the exhaustive sweeps.
    //
    // Playwright's own default is "wait forever", so a click on an element that
    // never becomes actionable hangs the run with no output rather than failing
    // the case. The first crawl run did exactly that.
    //
    // The BOUNDED specs (surfaces, graph, journeys, tours, overview) narrow
    // this to 5s with their own `test.use`, because there a timeout IS the
    // finding and fifteen seconds to learn something knowable in five is
    // minutes of nothing happening. It stays 15s here because the sweeps drive
    // hundreds of components and a heavy shard legitimately takes longer to
    // become clickable, which is a slowness worth reporting rather than a
    // failure worth manufacturing.
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: serveDir
    ? {
        command: `python3 -m http.server ${port} --bind 127.0.0.1 --directory ${serveDir}`,
        url: baseURL,
        reuseExistingServer: true,
        // http.server logs every request to stderr; piping it drowns the test
        // output. Failed requests are policed by the recorder, from the page
        // side, which is where the allowlist lives anyway.
        stdout: "ignore",
        stderr: "ignore",
      }
    : undefined,
});
