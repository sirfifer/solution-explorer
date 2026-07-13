import type { Env, IngestPayload, HealthResponse, ResourceUsage } from "./types";
import { FREE_TIER_LIMITS, USAGE_THRESHOLDS } from "./types";
import { verifyWebhookSignature } from "./webhook";
import { safeComponentId } from "./componentId";

// --- In-memory resource usage cache ---
// Reset on cold start; refreshed from D1 every 100 requests.
let cachedUsage: ResourceUsage | null = null;
let cachedUsageDate: string | null = null;
let requestsSinceCacheRefresh = 0;

// --- CORS ---

const CORS_HEADERS: HeadersInit = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Hub-Signature-256",
  "Access-Control-Max-Age": "86400",
};

function jsonResponse(status: number, body?: unknown): Response {
  const headers = new Headers(CORS_HEADERS);
  if (body === undefined || body === null) {
    return new Response(null, { status, headers });
  }
  headers.set("Content-Type", "application/json");
  return new Response(JSON.stringify(body), { status, headers });
}

// --- Helpers ---

function todayString(): string {
  return new Date().toISOString().slice(0, 10);
}

function nowISO(): string {
  return new Date().toISOString();
}

const tokenEncoder = new TextEncoder();

/**
 * Constant-time comparison of two secret strings. Both sides are hashed to a
 * fixed-length SHA-256 digest first, so neither the byte-by-byte comparison nor
 * the length of the presented token leaks timing information about the expected
 * token. Equal digests imply equal inputs (collision resistance).
 */
async function timingSafeEqualStrings(a: string, b: string): Promise<boolean> {
  const [ha, hb] = await Promise.all([
    crypto.subtle.digest("SHA-256", tokenEncoder.encode(a)),
    crypto.subtle.digest("SHA-256", tokenEncoder.encode(b)),
  ]);
  const va = new Uint8Array(ha);
  const vb = new Uint8Array(hb);
  let result = 0;
  for (let i = 0; i < va.length; i++) {
    result |= va[i] ^ vb[i];
  }
  return result === 0;
}

export async function validateBearerToken(
  request: Request,
  expected: string,
): Promise<boolean> {
  const auth = request.headers.get("Authorization");
  if (!auth?.startsWith("Bearer ")) return false;
  return timingSafeEqualStrings(auth.slice(7), expected);
}

// --- Resource tracking ---

async function getUsageFromD1(
  db: D1Database,
  projectId: string,
  date: string,
): Promise<ResourceUsage> {
  const row = await db
    .prepare(
      "SELECT worker_requests, d1_reads, d1_writes, r2_reads, r2_writes FROM resource_usage WHERE project_id = ? AND date = ?",
    )
    .bind(projectId, date)
    .first<ResourceUsage>();
  return row ?? { worker_requests: 0, d1_reads: 0, d1_writes: 0, r2_reads: 0, r2_writes: 0 };
}

async function incrementUsage(
  db: D1Database,
  projectId: string,
  field: keyof ResourceUsage,
  count = 1,
): Promise<void> {
  const date = todayString();
  await db
    .prepare(
      `INSERT INTO resource_usage (project_id, date, ${field})
       VALUES (?, ?, ?)
       ON CONFLICT(project_id, date) DO UPDATE SET ${field} = ${field} + ?`,
    )
    .bind(projectId, date, count, count)
    .run();
}

/**
 * Check whether the worker should accept this request based on free tier limits.
 * Uses an in-memory cache to minimize D1 reads (refreshed on cold start or every 100 requests).
 * Returns true if within limits, false if throttled.
 */
async function checkResourceLimits(
  db: D1Database,
  projectId: string,
): Promise<boolean> {
  const date = todayString();

  if (cachedUsage && cachedUsageDate === date && requestsSinceCacheRefresh < 100) {
    requestsSinceCacheRefresh++;
    if (cachedUsage.worker_requests >= USAGE_THRESHOLDS.worker_requests_per_day) {
      return false;
    }
    cachedUsage.worker_requests++;
    return true;
  }

  // Refresh from D1
  cachedUsage = await getUsageFromD1(db, projectId, date);
  cachedUsageDate = date;
  requestsSinceCacheRefresh = 1;

  if (cachedUsage.worker_requests >= USAGE_THRESHOLDS.worker_requests_per_day) {
    return false;
  }
  cachedUsage.worker_requests++;
  return true;
}

// --- Route handlers ---

async function handleIngest(request: Request, env: Env): Promise<Response> {
  if (!(await validateBearerToken(request, env.INGEST_TOKEN))) {
    return jsonResponse(401, { error: "Unauthorized" });
  }

  let payload: IngestPayload;
  try {
    payload = (await request.json()) as IngestPayload;
  } catch {
    return jsonResponse(400, { error: "Invalid JSON body" });
  }

  if (!payload.project_id || !payload.commit_sha || payload.version === undefined) {
    return jsonResponse(400, {
      error: "Missing required fields: project_id, commit_sha, version",
    });
  }

  const projectId = payload.project_id;

  try {
    // 1. Write version record to D1
    await env.DB.prepare(
      "INSERT INTO versions (project_id, version, commit_sha, component_count, relationship_count) VALUES (?, ?, ?, ?, ?)",
    )
      .bind(
        projectId,
        payload.version,
        payload.commit_sha,
        payload.component_count ?? 0,
        payload.relationship_count ?? 0,
      )
      .run();

    // 2. Write patch record if diff_summary provided
    if (payload.diff_summary) {
      const d = payload.diff_summary;
      await env.DB.prepare(
        "INSERT INTO patches (project_id, version, commit_sha, commit_message, components_added, components_removed, components_modified, relationships_changed, files_changed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
      )
        .bind(
          projectId,
          payload.version,
          payload.commit_sha,
          payload.commit_message ?? "",
          d.components_added,
          d.components_removed,
          d.components_modified,
          d.relationships_changed,
          d.files_changed,
        )
        .run();
    }

    // 3. Upsert health record
    await env.DB.prepare(
      `INSERT INTO health (project_id, last_update, version, component_count, relationship_count, status)
       VALUES (?, ?, ?, ?, ?, 'ok')
       ON CONFLICT(project_id) DO UPDATE SET
         last_update = excluded.last_update,
         version = excluded.version,
         component_count = excluded.component_count,
         relationship_count = excluded.relationship_count,
         status = 'ok',
         error_message = NULL`,
    )
      .bind(
        projectId,
        nowISO(),
        payload.version,
        payload.component_count ?? 0,
        payload.relationship_count ?? 0,
      )
      .run();

    // 4. Regenerate admin-summary.json in R2
    await regenerateAdminSummary(env, projectId);

    // 5. Update version.json in R2 (triggers viewer poll detection)
    await env.BUCKET.put(
      `${projectId}/version.json`,
      JSON.stringify({
        version: payload.version,
        updated_at: nowISO(),
        commit_sha: payload.commit_sha,
      }),
      { httpMetadata: { contentType: "application/json" } },
    );

    // 6. Clean up orphaned detail files in R2
    if (payload.component_ids && payload.component_ids.length > 0) {
      await cleanupOrphanedDetails(env.BUCKET, projectId, payload.component_ids);
    }

    // Track resource usage
    await incrementUsage(env.DB, projectId, "d1_writes", 4);
    await incrementUsage(env.DB, projectId, "r2_writes", 3);

    return jsonResponse(204);
  } catch (err) {
    // Record error in health table (best effort)
    try {
      await env.DB.prepare(
        "UPDATE health SET status = 'error', error_message = ? WHERE project_id = ?",
      )
        .bind(err instanceof Error ? err.message : "Unknown error", projectId)
        .run();
    } catch {
      // Best effort
    }
    return jsonResponse(500, { error: "Internal error during ingestion" });
  }
}

async function regenerateAdminSummary(env: Env, projectId: string): Promise<void> {
  const health = await env.DB.prepare(
    "SELECT * FROM health WHERE project_id = ?",
  )
    .bind(projectId)
    .first<Record<string, unknown>>();

  const patches = await env.DB.prepare(
    "SELECT * FROM patches WHERE project_id = ? ORDER BY created_at DESC LIMIT 20",
  )
    .bind(projectId)
    .all<Record<string, unknown>>();

  const dailyCounts = await env.DB.prepare(
    `SELECT substr(created_at, 1, 10) as date, COUNT(*) as count
     FROM patches WHERE project_id = ?
     GROUP BY date ORDER BY date DESC LIMIT 30`,
  )
    .bind(projectId)
    .all<{ date: string; count: number }>();

  const usage = await getUsageFromD1(env.DB, projectId, todayString());

  const summary = {
    repos: health
      ? [
          {
            name: projectId,
            last_update: health.last_update as string,
            version: health.version as number,
            component_count: health.component_count as number,
            status: health.status as string,
            error_message: health.error_message as string | undefined,
          },
        ]
      : [],
    activity: (patches.results ?? []).map((p) => ({
      timestamp: p.created_at as string,
      commit_sha: p.commit_sha as string,
      commit_message: p.commit_message as string,
      diff_summary: {
        components_added: p.components_added as number,
        components_removed: p.components_removed as number,
        components_modified: p.components_modified as number,
        relationships_changed: p.relationships_changed as number,
        files_changed: p.files_changed as number,
      },
    })),
    daily_counts: Object.fromEntries(
      (dailyCounts.results ?? []).map((r) => [r.date, r.count]),
    ),
    resource_usage: {
      worker_requests: usage.worker_requests,
      d1_reads: usage.d1_reads,
      d1_writes: usage.d1_writes,
      r2_reads: usage.r2_reads,
      r2_writes: usage.r2_writes,
      limits: {
        worker_requests_per_day: FREE_TIER_LIMITS.worker_requests_per_day,
        d1_reads_per_day: FREE_TIER_LIMITS.d1_reads_per_day,
        d1_writes_per_day: FREE_TIER_LIMITS.d1_writes_per_day,
        r2_reads_per_month: FREE_TIER_LIMITS.r2_reads_per_month,
        r2_writes_per_month: FREE_TIER_LIMITS.r2_writes_per_month,
      },
    },
    generated_at: nowISO(),
  };

  await env.BUCKET.put(
    `${projectId}/admin-summary.json`,
    JSON.stringify(summary),
    { httpMetadata: { contentType: "application/json" } },
  );
}

async function cleanupOrphanedDetails(
  bucket: R2Bucket,
  projectId: string,
  activeComponentIds: string[],
): Promise<void> {
  const prefix = `${projectId}/detail-`;
  const listed = await bucket.list({ prefix });

  const activeKeys = new Set(
    activeComponentIds.map(
      (id) => `${projectId}/detail-${safeComponentId(id)}.json`,
    ),
  );

  for (const obj of listed.objects) {
    if (!activeKeys.has(obj.key)) {
      await bucket.delete(obj.key);
    }
  }
}

async function handleWebhook(request: Request, env: Env): Promise<Response> {
  const signature = request.headers.get("X-Hub-Signature-256");
  if (!signature) {
    return jsonResponse(401, { error: "Missing signature header" });
  }

  const body = await request.text();
  const valid = await verifyWebhookSignature(body, signature, env.WEBHOOK_SECRET);
  if (!valid) {
    return jsonResponse(403, { error: "Invalid signature" });
  }

  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(body) as Record<string, unknown>;
  } catch {
    return jsonResponse(400, { error: "Invalid JSON" });
  }

  const event = request.headers.get("X-GitHub-Event");

  if (event !== "workflow_run") {
    return jsonResponse(200, { status: "ignored", event });
  }

  const workflowRun = payload.workflow_run as Record<string, unknown> | undefined;
  if (!workflowRun) {
    return jsonResponse(200, { status: "ignored", reason: "no workflow_run" });
  }

  const conclusion = workflowRun.conclusion as string | null;
  const status = workflowRun.status as string | null;
  const name = workflowRun.name as string;
  const htmlUrl = workflowRun.html_url as string;
  const updatedAt = workflowRun.updated_at as string;
  const headSha = workflowRun.head_sha as string;

  // Map conclusion to status level (matching collect-ci-status.py)
  const conclusionMap: Record<string, string> = {
    success: "ok",
    failure: "error",
    timed_out: "error",
    cancelled: "warning",
    skipped: "warning",
    action_required: "warning",
    stale: "warning",
    neutral: "ok",
    startup_failure: "error",
  };

  let level: string;
  if (conclusion === null) {
    level = status === "in_progress" || status === "queued" ? "info" : "warning";
  } else {
    level = conclusionMap[conclusion] ?? "warning";
  }

  // Derive project_id from repository name
  const repo = payload.repository as Record<string, unknown> | undefined;
  const repoName = (repo?.name as string) ?? "unknown";
  const projectId = repoName;

  const slugifiedName = name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

  // Read or create status-overlay.json in R2
  let overlay: Record<string, unknown>;
  try {
    const existing = await env.BUCKET.get(`${projectId}/status-overlay.json`);
    overlay = existing
      ? ((await existing.json()) as Record<string, unknown>)
      : { components: {}, architecture: {}, updated_at: nowISO(), commit_sha: headSha };
  } catch {
    overlay = { components: {}, architecture: {}, updated_at: nowISO(), commit_sha: headSha };
  }

  const arch = (overlay.architecture ?? {}) as Record<string, unknown>;
  arch[`ci:${slugifiedName}`] = {
    level,
    title: conclusion ? `${name} ${conclusion}` : `${name} ${status ?? "in progress"}`,
    detail: `Workflow ${conclusion ?? status ?? "unknown"}`,
    url: htmlUrl,
    category: "ci",
    updated_at: updatedAt ?? nowISO(),
  };
  overlay.architecture = arch;
  overlay.updated_at = nowISO();
  overlay.commit_sha = headSha;

  await env.BUCKET.put(
    `${projectId}/status-overlay.json`,
    JSON.stringify(overlay),
    { httpMetadata: { contentType: "application/json" } },
  );

  // Bump version.json timestamp so viewer polls pick up the change
  try {
    const versionObj = await env.BUCKET.get(`${projectId}/version.json`);
    if (versionObj) {
      const versionData = (await versionObj.json()) as Record<string, unknown>;
      versionData.updated_at = nowISO();
      await env.BUCKET.put(
        `${projectId}/version.json`,
        JSON.stringify(versionData),
        { httpMetadata: { contentType: "application/json" } },
      );
    }
  } catch {
    // Best effort: version.json bump is not critical
  }

  await incrementUsage(env.DB, projectId, "r2_writes", 2);
  await incrementUsage(env.DB, projectId, "r2_reads", 2);

  return jsonResponse(200, { status: "processed", event, conclusion, level });
}

async function handleHealth(env: Env): Promise<Response> {
  let d1Status: "ok" | "error" = "ok";
  const r2Status: "ok" | "error" = "ok";

  try {
    await env.DB.prepare("SELECT 1").first();
  } catch {
    d1Status = "error";
  }

  // R2 health check: head() on a non-existent key returns null (not an error).
  // An actual R2 connection failure would throw. We skip this check to
  // avoid counting it as an R2 read against free tier.

  const body: HealthResponse = {
    worker_version: env.WORKER_VERSION ?? "1.0.0",
    d1_status: d1Status,
    r2_status: r2Status,
    timestamp: nowISO(),
  };

  return jsonResponse(200, body);
}

async function handleGetSettings(
  projectId: string,
  env: Env,
): Promise<Response> {
  const kvKey = `settings:${projectId}`;
  const kvValue = await env.SETTINGS_KV.get(kvKey);
  if (kvValue) {
    return jsonResponse(200, JSON.parse(kvValue));
  }

  return jsonResponse(200, {
    project_id: projectId,
    polling_interval: 30,
    features: {},
  });
}

async function handlePostSettings(
  request: Request,
  projectId: string,
  env: Env,
): Promise<Response> {
  if (!(await validateBearerToken(request, env.INGEST_TOKEN))) {
    return jsonResponse(401, { error: "Unauthorized" });
  }

  let settings: Record<string, unknown>;
  try {
    settings = (await request.json()) as Record<string, unknown>;
  } catch {
    return jsonResponse(400, { error: "Invalid JSON" });
  }

  settings.project_id = projectId;
  settings.updated_at = nowISO();

  const kvKey = `settings:${projectId}`;
  await env.SETTINGS_KV.put(kvKey, JSON.stringify(settings));

  return jsonResponse(200, settings);
}

// --- Main router ---

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return jsonResponse(204);
    }

    const url = new URL(request.url);
    const path = url.pathname;

    // Resource tracking middleware (skip for health to keep it lightweight)
    if (path !== "/health") {
      const trackingId = "default";
      const allowed = await checkResourceLimits(env.DB, trackingId);
      if (!allowed) {
        return jsonResponse(429, {
          error: "Free tier usage limit approaching. Requests are throttled.",
          retry_after_seconds: 3600,
        });
      }
      await incrementUsage(env.DB, trackingId, "worker_requests");
    }

    try {
      if (path === "/ingest" && request.method === "POST") {
        return await handleIngest(request, env);
      }

      if (path === "/webhook" && request.method === "POST") {
        return await handleWebhook(request, env);
      }

      if (path === "/health" && request.method === "GET") {
        return await handleHealth(env);
      }

      const settingsMatch = path.match(/^\/settings\/([a-zA-Z0-9_-]+)$/);
      if (settingsMatch) {
        const settingsProjectId = settingsMatch[1];
        if (request.method === "GET") {
          return await handleGetSettings(settingsProjectId, env);
        }
        if (request.method === "POST") {
          return await handlePostSettings(request, settingsProjectId, env);
        }
      }

      return jsonResponse(404, { error: "Not found" });
    } catch (err) {
      console.error("Unhandled error:", err);
      return jsonResponse(500, { error: "Internal server error" });
    }
  },
} satisfies ExportedHandler<Env>;
