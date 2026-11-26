#!/bin/bash
# 註冊並啟動 self-hosted GPU runner（需先 gh auth login 且對 repo 有 admin 權）。
# 用法: scripts/setup_runner.sh <owner/repo> [runner_dir]
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

REPO="${1:?用法: setup_runner.sh <owner/repo> [runner_dir]}"
RUNNER_DIR="${2:-$HOME/actions-runner}"
LABELS="${RUNNER_LABELS:-gpu}"

mkdir -p "$RUNNER_DIR"; cd "$RUNNER_DIR"

# 下載 actions runner（若尚未）
if [ ! -f ./config.sh ]; then
  VER=$(gh api repos/actions/runner/releases/latest -q .tag_name | sed 's/^v//')
  echo "下載 actions-runner v$VER …"
  curl -fsSL -o runner.tar.gz \
    "https://github.com/actions/runner/releases/download/v${VER}/actions-runner-linux-x64-${VER}.tar.gz"
  tar xzf runner.tar.gz && rm runner.tar.gz
fi

# 取註冊 token（短效，由 gh 代為申請）並設定
TOKEN=$(gh api -X POST "repos/${REPO}/actions/runners/registration-token" -q .token)
./config.sh --unattended --replace \
  --url "https://github.com/${REPO}" \
  --token "$TOKEN" \
  --labels "$LABELS" \
  --name "$(hostname)-rtx3060"

# 背景啟動（免 sudo；不跨重開機。要開機自啟用 sudo ./svc.sh install && sudo ./svc.sh start）
nohup ./run.sh > "$RUNNER_DIR/runner.log" 2>&1 &
sleep 2
echo "✅ runner 已啟動（label: $LABELS）；log: $RUNNER_DIR/runner.log"
