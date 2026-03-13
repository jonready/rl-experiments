#!/bin/bash
# Background loop: uploads new checkpoints to R2
# Expects: R2_ENDPOINT, R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET

set -euo pipefail

CHECKPOINT_DIR="${CHECKPOINT_DIR:-outputs/weights}"
SYNC_INTERVAL="${SYNC_INTERVAL:-30}"

echo "[sync] Watching $CHECKPOINT_DIR every ${SYNC_INTERVAL}s"

while true; do
    for dir in "$CHECKPOINT_DIR"/step_*/; do
        if [ -d "$dir" ] && [ ! -f "$dir/.uploaded" ]; then
            step=$(basename "$dir")
            echo "[sync] Uploading $step..."
            aws s3 sync "$dir" "s3://$R2_BUCKET/wordle/rl/$step/" \
                --endpoint-url "$R2_ENDPOINT" \
                --quiet
            if [ $? -eq 0 ]; then
                touch "$dir/.uploaded"
                echo "[sync] $step uploaded"
            else
                echo "[sync] $step upload failed, will retry"
            fi
        fi
    done
    sleep "$SYNC_INTERVAL"
done
