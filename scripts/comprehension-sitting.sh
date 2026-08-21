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
# Verified 2026-08-19: under this profile a session reports exactly
# ToolSearch, Write, TodoWrite, mcp__playwriter__execute, mcp__playwriter__reset.
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

mkdir -p "$DIR/evidence"
cat > "$DIR/.mcp.json" <<'JSON'
{
  "mcpServers": {
    "playwriter": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "playwriter@latest"],
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
  --allowedTools "mcp__playwriter,Write,TodoWrite" \
  --disallowedTools "$DENY" \
  < BRIEF.md 2>&1 | tee "$DIR/TRANSCRIPT.txt"

date -u +"end_utc=%Y-%m-%dT%H:%M:%SZ" | tee -a "$DIR/TIMING.txt"
echo "sitting $PERSONA complete: $DIR"
