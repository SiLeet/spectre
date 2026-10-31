#!/bin/bash
# Bounded repeatability test: run the claim wrapper N times with a pause between
# rounds, so the loop has to recover from whatever state the previous round left.
# Usage: scripts/afk-bot-soak.sh [rounds] [pause_seconds]
set -u
cd "$(dirname "$0")/.."
ROUNDS="${1:-3}"
PAUSE="${2:-200}"
for i in $(seq 1 "$ROUNDS"); do
  echo "--- round $i/$ROUNDS $(date -u +%H:%M:%S)"
  bash scripts/afk-bot-watch.sh 2>&1 | grep -E "afk-bot-watch|tap sequence|WARN|memory check" | head -5
  if [ "$i" -lt "$ROUNDS" ]; then sleep "$PAUSE"; fi
done
echo "=== soak done $(date -u +%H:%M:%S)"
