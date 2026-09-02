#!/usr/bin/env bash
# Launch one cold persona sitting for the Comprehension Review.
#
# Charter: docs/quality/COMPREHENSION-REVIEW.md, "Who can be a persona".
# A persona must have no exposure to this repository. That is the measurement,
# not a preference, so this script establishes coldness by construction rather
# than by instruction:
#
#   * a working directory outside this repository, so no repo file sits on any
#     relative path, no project CLAUDE.md loads, and the auto-memory directory
#     (keyed on the working directory) is a different, empty one
#   * --strict-mcp-config with a config granting only the browser, so no other
#     connector is reachable
#   * --disable-slash-commands, which removes the skill set, including the
#     unamentis skill that would otherwise describe the subject from our side
#   * a deny list that removes Read, Bash, Grep, Glob, WebFetch, WebSearch and
#     Agent. Without a file reader the persona cannot read the repository or
#     the served mirror's raw files, and without web tools it cannot look the
#     subject up instead of learning it from the site
#
# Transport, changed 2026-09-01: the browser is the standard Playwright MCP
# server, which launches and owns its own Chromium with --isolated (profile held
# in memory, never written to disk). It replaces the playwriter extension, which
# attached to the operator's already-running Chrome. That older transport made
# every sitting share one browser, forced sittings to run sequentially, required
# a manual extension click, and on 2026-09-01 degraded and then killed P1's tab
# at ~25 of 90 minutes, which in turn left P2 and P3 with no browser at all. The
# viewer was independently soak-tested over 60 lens cycles during that incident
# and showed a flat heap and constant render time, so the fault was the
# transport. Consequences of the change, both good: storage isolation is now
# structural rather than an instruction the persona must remember to follow,
# and sittings can run concurrently because no two share a browser.
#
# Verified 2026-08-19 on the previous transport: under this profile a session
# reports exactly the browser tools plus ToolSearch, Write and TodoWrite.
#
# Usage: comprehension-sitting.sh <persona> <url> <sitting-dir> <brief-file>

set -euo pipefail

PERSONA="${1:?persona id, e.g. P1}"
URL="${2:?url the persona browses}"
DIR="${3:?sitting directory, must be outside this repository}"
BRIEF="${4:?path to the persona brief}"
MODEL="${MODEL:-sonnet}"

case "$DIR" in
  *solution-explorer*)
    echo "REFUSED: the sitting directory names this repository ($DIR)." >&2
    echo "A persona that can see the repository's name is not cold." >&2
    exit 1 ;;
esac

mkdir -p "$DIR/evidence" "$DIR/artifacts"
cat > "$DIR/.mcp.json" <<JSON
{
  "mcpServers": {
    "playwright": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "-y", "@playwright/mcp@latest",
        "--isolated",
        "--headless",
        "--viewport-size", "1440x900",
        "--output-dir", "$DIR/artifacts"
      ],
      "env": {}
    }
  }
}
JSON

sed "s|@@URL@@|$URL|g" "$BRIEF" > "$DIR/BRIEF.md"

DENY="Read,Bash,Grep,Glob,Edit,NotebookEdit,WebFetch,WebSearch,Agent,Task"
DENY="$DENY,SendMessage,TaskOutput,TaskStop,Workflow,Artifact,Monitor,RemoteTrigger"
DENY="$DENY,CronCreate,CronList,CronDelete,PushNotification,ScheduleWakeup,DesignSync"
DENY="$DENY,EnterWorktree,ExitWorktree,ListMcpResourcesTool,ReadMcpResourceTool"
DENY="$DENY,ReadMcpResourceDirTool,ReportFindings"

echo "sitting $PERSONA: $URL  ->  $DIR  (model $MODEL)"
date -u +"start_utc=%Y-%m-%dT%H:%M:%SZ" | tee "$DIR/TIMING.txt"

cd "$DIR"
claude -p \
  --model "$MODEL" \
  --mcp-config .mcp.json \
  --strict-mcp-config \
  --disable-slash-commands \
  --permission-mode acceptEdits \
  --allowedTools "mcp__playwright,Write,TodoWrite" \
  --disallowedTools "$DENY" \
  < BRIEF.md 2>&1 | tee "$DIR/TRANSCRIPT.txt"

date -u +"end_utc=%Y-%m-%dT%H:%M:%SZ" | tee -a "$DIR/TIMING.txt"
echo "sitting $PERSONA complete: $DIR"
