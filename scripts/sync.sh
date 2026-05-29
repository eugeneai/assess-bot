#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/sync.sh pull|push [extra rsync args]

SERVER="${ASSESS_SERVER:-ktulhu}"
REMOTE_PATH="${ASSESS_REMOTE_PATH:-~/projects/code/deepseek/assess-bot}"
LOCAL="${ASSESS_LOCAL:-.}"

case "${1:-help}" in
  pull)
    rsync -avz --progress \
      "$SERVER:$REMOTE_PATH/assess.db" "$LOCAL/assess.db"
    rsync -avz --progress \
      "$SERVER:$REMOTE_PATH/files/" "$LOCAL/files/" \
      --include='PROMPT.md' --include='cost_stats.json' --include='*/PROMPT.md' \
      --exclude='*'
    echo "✅ Context pulled"
    ;;
  push)
    rsync -avz --progress \
      "$LOCAL/output/" "$SERVER:$REMOTE_PATH/output/"
    rsync -avz --progress \
      "$LOCAL/assess.db" "$SERVER:$REMOTE_PATH/assess.db"
    echo "✅ Grades pushed"
    ;;
  *)
    echo "Usage: $0 pull|push"
    exit 1
    ;;
esac
