#!/usr/bin/env bash
set -euo pipefail

# Cloudflare infrastructure provisioning for solution-explorer.
# Idempotent: safe to run multiple times.
#
# Prerequisites:
#   - wrangler CLI installed and authenticated (`wrangler login`)
#
# Usage:
#   cd infrastructure/cloudflare
#   bash setup.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_DIR="$SCRIPT_DIR/worker"

echo "=== Solution Explorer: Cloudflare Infrastructure Setup ==="
echo ""

cd "$WORKER_DIR"

# 1. Create D1 database
echo "[1/7] Creating D1 database..."
D1_OUTPUT=$(wrangler d1 create solution-explorer-db 2>&1 || true)
echo "$D1_OUTPUT"

D1_ID=$(echo "$D1_OUTPUT" | grep -o 'database_id = "[^"]*"' | head -1 | sed 's/database_id = "//;s/"//' || true)
if [ -n "$D1_ID" ]; then
  echo "  Database ID: $D1_ID"
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/REPLACE_AFTER_D1_CREATION/$D1_ID/" wrangler.toml
  else
    sed -i "s/REPLACE_AFTER_D1_CREATION/$D1_ID/" wrangler.toml
  fi
  echo "  Updated wrangler.toml with database ID"
fi

# 2. Create R2 bucket
echo ""
echo "[2/7] Creating R2 bucket..."
wrangler r2 bucket create solution-explorer-data 2>&1 || echo "  (Bucket may already exist)"

# 3. Create KV namespace
echo ""
echo "[3/7] Creating KV namespace..."
KV_OUTPUT=$(wrangler kv namespace create SETTINGS_KV 2>&1 || true)
echo "$KV_OUTPUT"

KV_ID=$(echo "$KV_OUTPUT" | grep -o 'id = "[^"]*"' | head -1 | sed 's/id = "//;s/"//' || true)
if [ -n "$KV_ID" ]; then
  echo "  KV Namespace ID: $KV_ID"
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/REPLACE_AFTER_KV_CREATION/$KV_ID/" wrangler.toml
  else
    sed -i "s/REPLACE_AFTER_KV_CREATION/$KV_ID/" wrangler.toml
  fi
  echo "  Updated wrangler.toml with KV namespace ID"
fi

# 4. Apply D1 schema
echo ""
echo "[4/7] Applying D1 schema..."
wrangler d1 execute solution-explorer-db --file=schema.sql

# 5. Set secrets
echo ""
echo "[5/7] Setting secrets..."
echo ""
echo "  INGEST_TOKEN: Bearer token for the /ingest endpoint."
echo "  Generate one with: openssl rand -hex 32"
wrangler secret put INGEST_TOKEN
echo ""
echo "  WEBHOOK_SECRET: Must match the secret configured in GitHub webhook settings."
wrangler secret put WEBHOOK_SECRET

# 6. Install dependencies
echo ""
echo "[6/7] Installing dependencies..."
npm install

# 7. Deploy
echo ""
echo "[7/7] Deploying worker..."
wrangler deploy

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Note the deployed worker URL shown above"
echo "  2. Configure a GitHub webhook:"
echo "     - URL: <worker-url>/webhook"
echo "     - Content type: application/json"
echo "     - Secret: the WEBHOOK_SECRET you entered above"
echo "     - Events: Workflow runs"
echo "  3. Add these secrets to your GitHub repository:"
echo "     - CF_R2_ACCESS_KEY_ID"
echo "     - CF_R2_SECRET_ACCESS_KEY"
echo "     - CF_R2_ENDPOINT  (https://<account-id>.r2.cloudflarestorage.com)"
echo "     - CF_WORKER_URL   (the deployed worker URL)"
echo "     - CF_INGEST_TOKEN (the INGEST_TOKEN you entered above)"
