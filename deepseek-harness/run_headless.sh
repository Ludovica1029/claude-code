#!/usr/bin/env bash
# 用 dsh 的 headless profile 跑一个一次性任务。
#   真实模型：export DEEPSEEK_API_KEY=sk-...  然后 ./run_headless.sh "你的任务"
#   本地 mock： MOCK=1 ./run_headless.sh
set -euo pipefail
cd "$(dirname "$0")"
[ -d node_modules ] || npm install
export DSH_HOME="${DSH_HOME:-$PWD/.dsh-home}"   # 隔离的 Harness home，不碰 ~/.dsh
if [ "${MOCK:-0}" = 1 ]; then
  node mock_llm.mjs 8787 mock-requests.jsonl & MOCK_PID=$!
  trap 'kill $MOCK_PID' EXIT
  sleep 1
  export DEEPSEEK_API_KEY=fake DEEPSEEK_BASE_URL=http://127.0.0.1:8787 NO_PROXY=127.0.0.1 no_proxy=127.0.0.1
fi
mkdir -p workspace && cd workspace
time npx --prefix .. dsh headless --json "${1:-create out.txt with hello}"
