#!/bin/bash
# Runs on the spot instance (pre-built image): configure credentials, run SFT then RL, sync checkpoints to R2
# Expects env vars: R2_ENDPOINT, R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET, RESUME (0 or 1)

set -euo pipefail

export PATH="/root/.local/bin:$PATH"
cd /opt/prime-rl

RESUME="${RESUME:-0}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Configure AWS CLI for R2 ---
echo "=== Configuring AWS CLI for R2 ==="
mkdir -p ~/.aws
cat > ~/.aws/credentials <<EOF
[default]
aws_access_key_id = $R2_ACCESS_KEY
aws_secret_access_key = $R2_SECRET_KEY
EOF
cat > ~/.aws/config <<EOF
[default]
region = auto
EOF

# --- SFT or Resume ---
if [ "$RESUME" = "0" ]; then
    echo "=== Running SFT ==="
    uv run sft @ "$SCRIPT_DIR/configs/sft_spot.toml"

    echo "=== Uploading SFT weights to R2 ==="
    SFT_DIR=$(ls -d outputs/weights/step_* 2>/dev/null | tail -1)
    if [ -n "$SFT_DIR" ]; then
        aws s3 sync "$SFT_DIR" "s3://$R2_BUCKET/wordle/sft/final/" \
            --endpoint-url "$R2_ENDPOINT"
        echo "SFT weights uploaded"
    fi
else
    echo "=== Resuming: downloading SFT weights from R2 ==="
    mkdir -p outputs/sft
    aws s3 sync "s3://$R2_BUCKET/wordle/sft/final/" outputs/sft/final/ \
        --endpoint-url "$R2_ENDPOINT"
fi

# --- Checkpoint sync ---
echo "=== Starting checkpoint sync ==="
bash "$SCRIPT_DIR/sync_checkpoints.sh" &
SYNC_PID=$!
trap "kill $SYNC_PID 2>/dev/null" EXIT

# --- RL Training ---
echo "=== Running RL ==="
RL_ARGS=""
if [ "$RESUME" = "1" ]; then
    RL_ARGS="--ckpt.resume-step -1"
fi

uv run rl @ "$SCRIPT_DIR/configs/rl_spot.toml" $RL_ARGS

# --- Final sync ---
echo "=== Training complete ==="
sleep 5
kill $SYNC_PID 2>/dev/null || true
for dir in outputs/weights/step_*/; do
    if [ -d "$dir" ] && [ ! -f "$dir/.uploaded" ]; then
        step=$(basename "$dir")
        aws s3 sync "$dir" "s3://$R2_BUCKET/wordle/rl/$step/" --endpoint-url "$R2_ENDPOINT"
        touch "$dir/.uploaded"
    fi
done
echo "=== All checkpoints synced ==="
