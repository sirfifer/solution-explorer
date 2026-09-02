# Cloudflare Infrastructure for SysCorpus

Optional Cloudflare-enhanced backend that provides real-time CI status updates and faster data hosting compared to GitHub Pages alone.

## Architecture

```
GitHub Actions (compute layer)
  |
  +--> R2 bucket (data hosting, instant availability)
  +--> Worker /ingest (metadata to D1, triggers admin-summary regeneration)
  |
GitHub Webhooks
  +--> Worker /webhook (real-time CI status to R2)
  |
Viewer (polls R2 version.json every 10-60s)
```

- **R2**: Hosts architecture JSON files with instant availability (no CDN cache delay)
- **D1**: Stores version history, patch diffs, health status, and resource usage
- **Worker**: Receives webhook events and ingest calls, manages R2/D1 data
- **KV**: Caches per-project settings

## Prerequisites

- A Cloudflare account (free tier is sufficient)
- `wrangler` CLI installed: `npm install -g wrangler`
- Authenticated: `wrangler login`

## Setup

Run the provisioning script from this directory:

```bash
bash setup.sh
```

The script creates all required resources (D1 database, R2 bucket, KV namespace), applies the database schema, prompts for secrets, and deploys the worker.

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/ingest` | Bearer token | Called by GitHub Actions after R2 upload. Writes metadata to D1, regenerates admin summary, cleans up orphaned detail files. |
| POST | `/webhook` | HMAC signature | Receives GitHub `workflow_run` webhooks. Updates CI status overlay in R2. |
| GET | `/health` | None | Returns worker version and D1/R2 connectivity status. |
| GET | `/settings/:id` | None | Returns project settings from KV. |
| POST | `/settings/:id` | Bearer token | Updates project settings in KV. |

## GitHub Actions Secrets

After running `setup.sh`, add these secrets to your GitHub repository:

| Secret | Description |
|--------|-------------|
| `CF_R2_ACCESS_KEY_ID` | R2 API token access key ID |
| `CF_R2_SECRET_ACCESS_KEY` | R2 API token secret access key |
| `CF_R2_ENDPOINT` | `https://<account-id>.r2.cloudflarestorage.com` |
| `CF_WORKER_URL` | Deployed worker URL (e.g., `https://solution-explorer-api.<you>.workers.dev`) |
| `CF_INGEST_TOKEN` | The INGEST_TOKEN you set during setup |

When `CF_WORKER_URL` is set, the live-monitor workflow automatically uploads to R2 and notifies the worker. When it is not set, the workflow uses GitHub Pages only.

## Free Tier Limits

The worker tracks resource usage and self-throttles at 80% of Cloudflare free tier limits:

| Resource | Free Tier | Throttle At |
|----------|-----------|-------------|
| Worker requests/day | 100,000 | 80,000 |
| D1 writes/day | 100,000 | 80,000 |
| D1 reads/day | 5,000,000 | (not throttled) |
| R2 reads/month | 10,000,000 | (tracked only) |
| R2 writes/month | 1,000,000 | (tracked only) |

Resource usage is visible in the admin dashboard's Resources tab.

## Troubleshooting

**Worker returns 429**: Free tier limits are approaching. Usage resets daily for worker/D1 requests. Check the admin dashboard Resources tab for current usage.

**Webhook not processing**: Verify the webhook secret matches the `WEBHOOK_SECRET` set in the worker. Check that the webhook is configured for "Workflow runs" events. Use `curl localhost:8787/health` during local dev to verify connectivity.

**D1 schema errors**: Re-run `wrangler d1 execute solution-explorer-db --file=worker/schema.sql` from this directory. The schema uses `IF NOT EXISTS` so it is safe to re-apply.

**Local development**: Run `cd worker && npm run dev` to start a local worker. D1 and R2 are simulated locally by wrangler.
