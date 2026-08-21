#!/usr/bin/env bash
# Authenticated Cloudflare API caller, backed by the macOS login Keychain.
#
# WHY THIS EXISTS
#
# Privileged Cloudflare work kept needing a round trip through GitHub Actions,
# because that is where CLOUDFLARE_API_TOKEN lives and Actions secrets cannot be
# read back out. That works but it is slow, it needs a workflow on the default
# branch for every new operation, and it cannot be used for exploration. wrangler
# covers deploys and secrets but has no custom-domain command at any version
# through 4.125.0, so anything else needs the REST API, which needs a token.
#
# The wrong fixes, and why:
#   - `export CLOUDFLARE_API_TOKEN=...` in a shell or dotfile: moves a long-lived
#     credential into plaintext on disk and into every child process. A downgrade
#     in posture for convenience.
#   - Reading the token into an agent's context to use it: the secret ends up in
#     a transcript. Secrets should be USED, never READ.
#
# WHAT THIS DOES
#
# The token lives in the login Keychain (encrypted at rest, ACL'd per app, the
# same store the OS uses for its own credentials). This script fetches it inside
# its own process, passes it straight to curl, and never prints it. The value is
# never echoed, never written to a file, never returned to a caller. `set +x` is
# forced so a caller running under `bash -x` cannot leak it either.
#
# BOOTSTRAP (once per machine)
#
#   scripts/cf-api.sh --store        # prompts, does not echo, writes to Keychain
#
# or non-interactively from another secure source:
#
#   printf '%s' "$TOKEN" | scripts/cf-api.sh --store-stdin
#
# USAGE
#
#   scripts/cf-api.sh GET  /accounts/{acct}/pages/projects
#   scripts/cf-api.sh POST /accounts/{acct}/pages/projects/foo/domains '{"name":"a.b.com"}'
#   scripts/cf-api.sh --check                    # verify the stored token works
#
# The account id is not a secret (it appears in dashboard URLs) and is exported
# as CF_ACCOUNT_ID for convenience, so paths can use ${CF_ACCOUNT_ID}.

set -euo pipefail
set +x  # never trace: a traced run would print the token

KEYCHAIN_SERVICE="solution-explorer-cloudflare"
KEYCHAIN_ACCOUNT="api-token"
CF_ACCOUNT_ID="${CF_ACCOUNT_ID:-a01622cc6f94a7bb946140c02b6ee474}"
export CF_ACCOUNT_ID
API="https://api.cloudflare.com/client/v4"

die() { echo "error: $*" >&2; exit 1; }

_store() {
  local token="$1"
  [ -n "$token" ] || die "empty token; nothing stored"
  # -U updates in place if it already exists, so re-running is safe.
  security add-generic-password \
    -s "$KEYCHAIN_SERVICE" -a "$KEYCHAIN_ACCOUNT" -w "$token" -U \
    || die "could not write to the Keychain"
  echo "stored in the login Keychain as ${KEYCHAIN_SERVICE}/${KEYCHAIN_ACCOUNT}"
  echo "verifying it actually works..."
  _check
}

# Loads the token into the global TOKEN. Deliberately NOT a function that echoes
# it: `$(_token)` runs in a subshell, so a `die` inside it cannot stop the
# caller, and the first version of this script sailed past a missing token and
# sent an empty Authorization header. Assigning a global keeps the failure fatal
# in the process that matters, and fetches the secret exactly once per run.
_load_token() {
  TOKEN=$(security find-generic-password -s "$KEYCHAIN_SERVICE" -a "$KEYCHAIN_ACCOUNT" -w 2>/dev/null) \
    || die "no token in the Keychain. Bootstrap it once with: scripts/cf-api.sh --store"
  [ -n "$TOKEN" ] || die "the Keychain entry ${KEYCHAIN_SERVICE}/${KEYCHAIN_ACCOUNT} is empty"
}

_check() {
  local code
  _load_token
  code=$(curl -sS -o /tmp/cf-verify.$$ -w '%{http_code}' \
    "$API/user/tokens/verify" \
    -H "Authorization: Bearer $TOKEN")
  if [ "$code" = "200" ]; then
    # Print only the non-sensitive status, never the token or its id.
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); r=d.get("result") or {}; print("token status:", r.get("status"), "| expires:", r.get("expires_on") or "never")' /tmp/cf-verify.$$
    rm -f /tmp/cf-verify.$$
    return 0
  fi
  rm -f /tmp/cf-verify.$$
  die "token verify returned HTTP $code; the stored token is missing, expired or revoked"
}

case "${1:-}" in
  --store)
    # -s reads silently; the value is never echoed to the terminal or to history.
    printf 'Paste the Cloudflare API token (input hidden), then press Return: ' >&2
    read -r -s _tok
    printf '\n' >&2
    _store "$_tok"
    unset _tok
    exit 0
    ;;
  --store-stdin)
    _store "$(cat)"
    exit 0
    ;;
  --check)
    _check
    exit 0
    ;;
  GET|POST|PUT|PATCH|DELETE)
    method="$1"
    path="${2:?usage: cf-api.sh <METHOD> <path> [json-body]}"
    body="${3:-}"
    _load_token
    args=(-sS -X "$method" "${API}${path}"
          -H "Authorization: Bearer $TOKEN"
          -H "Content-Type: application/json")
    [ -n "$body" ] && args+=(--data "$body")
    curl "${args[@]}"
    echo
    exit 0
    ;;
  *)
    sed -n '2,45p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
