#!/usr/bin/env bash
# on-session-end.sh — agent-hooks shell listener for session.lifecycle.end
# Runs minutes extraction on the session transcript.
#
# Receives event JSON on stdin with:
#   data.session_file  — path to session JSONL transcript
#   data.project_key   — project identifier (e.g., -Users-danieliser-Toolkit)
#   data.duration       — session duration in seconds
#
# Returns JSON status on stdout for agent-hooks.

set -euo pipefail

PAYLOAD=$(cat)

# Extract fields
SESSION_FILE=$(echo "$PAYLOAD" | jq -r '.data.session_file // empty')
PROJECT_KEY=$(echo "$PAYLOAD" | jq -r '.data.project_key // empty')
DURATION=$(echo "$PAYLOAD" | jq -r '.data.duration // 0')

# Skip if no session file
if [[ -z "$SESSION_FILE" || ! -f "$SESSION_FILE" ]]; then
  echo '{"status": "skipped", "reason": "no session file"}'
  exit 0
fi

# Skip short sessions (< 2 minutes)
if (( DURATION < 120 )); then
  echo '{"status": "skipped", "reason": "session too short ('$DURATION's)"}'
  exit 0
fi

# Check gateway availability
if ! (echo >/dev/tcp/localhost/8800) 2>/dev/null; then
  echo '{"status": "skipped", "reason": "gateway not running"}'
  exit 0
fi

# Run extraction
OUTPUT_DIR="$HOME/.claude/minutes/${PROJECT_KEY}"
mkdir -p "$OUTPUT_DIR"

# Check that minutes CLI is available
if ! command -v minutes &>/dev/null; then
  echo '{"status": "error", "reason": "minutes not installed (pip install take-minutes)"}'
  exit 1
fi

# Run in background with all fds detached so agent-hooks doesn't wait
nohup minutes process "$SESSION_FILE" \
  -o "$OUTPUT_DIR" \
  >"$OUTPUT_DIR/.last-run.log" 2>&1 &

echo "{\"status\": \"started\", \"pid\": $!, \"output_dir\": \"$OUTPUT_DIR\"}"
