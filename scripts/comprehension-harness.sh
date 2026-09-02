#!/usr/bin/env bash
# Stand up the isolated serving environment for a Comprehension Review run.
#
# A sitting must be unable to disturb anything else on the machine, and nothing
# else on the machine must be able to disturb a sitting. That is a hard
# requirement of the instrument, not a convenience: a run that another process
# can perturb is not a measurement. This script is where that property is
# established and, more importantly, where it is CHECKED rather than assumed.
#
# What it guarantees:
#
#   * The mirror is a frozen production build in a stable directory of its own,
#     not a dev server and not a session scratch path that can vanish mid-run.
#   * Every persona port is verified, before any sitting launches, to be serving
#     THIS build, by comparing a content hash. A port squatted by unrelated work
#     is a loud failure instead of a sitting that silently measures the wrong
#     thing.
#   * Servers bind 127.0.0.1 only, so nothing off this machine can reach them.
#   * Only the servers this script started are ever stopped, tracked by pidfile,
#     so `down` cannot kill someone else's process that happens to hold a port.
#
# The browser side of the isolation lives in comprehension-sitting.sh: each
# sitting gets its own headless Chromium with an in-memory profile, so sittings
# neither share state with each other nor touch the operator's own browser.
#
# Usage:
#   comprehension-harness.sh build <viewer-dir>     freeze a mirror
#   comprehension-harness.sh up <port> [port ...]   serve it, verified
#   comprehension-harness.sh preflight <port> ...   re-verify before launching
#   comprehension-harness.sh down                   stop only our servers

set -euo pipefail

MIRROR="${COMPREHENSION_MIRROR:-/private/tmp/comprehension-mirror}"
PIDFILE="$MIRROR/.servers.pid"
SENTINEL="$MIRROR/.sentinel"

hash_build() { find "$MIRROR/site" -type f ! -name '.*' -exec shasum -a 256 {} + | awk '{print $1}' | sort | shasum -a 256 | awk '{print $1}'; }

cmd_build() {
  local viewer="${1:?path to the viewer directory}"
  [ -d "$viewer" ] || { echo "no such viewer directory: $viewer" >&2; exit 1; }
  rm -rf "$MIRROR/site"; mkdir -p "$MIRROR/site"
  ( cd "$viewer" && npx vite build --outDir "$MIRROR/site" --emptyOutDir >/dev/null 2>&1 ) \
    || { echo "build failed" >&2; exit 1; }
  hash_build > "$SENTINEL"
  echo "built $(find "$MIRROR/site" -type f | wc -l | tr -d ' ') files into $MIRROR/site"
  echo "sentinel $(cat "$SENTINEL")"
}

serves_our_build() {
  local port="$1"
  local got want
  want=$(shasum -a 256 "$MIRROR/site/index.html" | awk '{print $1}')
  got=$(curl -fsS --max-time 5 "http://127.0.0.1:$port/index.html" 2>/dev/null | shasum -a 256 | awk '{print $1}') || return 1
  [ "$got" = "$want" ]
}

cmd_up() {
  [ -s "$SENTINEL" ] || { echo "no frozen mirror; run 'build' first" >&2; exit 1; }
  : > "$PIDFILE"
  for port in "$@"; do
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      if serves_our_build "$port"; then
        echo "port $port already serving this build, reusing"; continue
      fi
      echo "REFUSED: port $port is held by something that is not this build." >&2
      echo "Pick another port. A sitting on a squatted port measures the wrong thing." >&2
      exit 1
    fi
    # exec so the recorded pid is the server itself, not a wrapper subshell;
    # `down` verifies the pid is still an http.server before signalling it.
    ( cd "$MIRROR/site" && exec nohup python3 -m http.server "$port" --bind 127.0.0.1 >"$MIRROR/serve-$port.log" 2>&1 ) &
    echo $! >> "$PIDFILE"
  done
  sleep 2
  cmd_preflight "$@"
}

cmd_preflight() {
  local bad=0
  for port in "$@"; do
    if serves_our_build "$port"; then
      echo "port $port OK, serving the frozen build"
    else
      echo "port $port FAILED verification" >&2; bad=1
    fi
  done
  [ "$bad" -eq 0 ] || { echo "preflight failed; do not launch sittings" >&2; exit 1; }
  echo "preflight passed for: $*"
}

cmd_down() {
  [ -s "$PIDFILE" ] || { echo "no servers recorded as started by this harness"; return 0; }
  while read -r pid; do
    [ -n "$pid" ] || continue
    if ps -o command= -p "$pid" 2>/dev/null | grep -q "http.server"; then
      kill "$pid" 2>/dev/null && echo "stopped $pid"
    else
      echo "pid $pid is not one of our servers any more, leaving it alone"
    fi
  done < "$PIDFILE"
  : > "$PIDFILE"
}

case "${1:?build|up|preflight|down}" in
  build)     shift; cmd_build "$@" ;;
  up)        shift; cmd_up "$@" ;;
  preflight) shift; cmd_preflight "$@" ;;
  down)      shift; cmd_down "$@" ;;
  *) echo "unknown command: $1" >&2; exit 1 ;;
esac
