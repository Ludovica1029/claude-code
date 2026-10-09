#!/usr/bin/env bash
# 一键启动：首次运行会建虚拟环境、装依赖、询问密钥并保存到 .env，之后直接启动。
set -e
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

if [ ! -d .venv ]; then
  echo "== 创建虚拟环境并安装依赖 =="
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

if [ ! -f .env ]; then
  echo "== 首次配置（输入内容不会显示，粘贴后直接回车）=="
  read -r -p "飞书 App ID [cli_aa365e8b88f91bef]: " APP_ID < /dev/tty
  read -r -s -p "飞书 App Secret: " APP_SECRET < /dev/tty; echo
  read -r -s -p "Claude API Key: " API_KEY < /dev/tty; echo
  read -r -p "API 地址（官方 Key 直接回车；中转站填它给的地址，如 https://xxx.com）: " BASE_URL < /dev/tty
  read -r -p "模型名 [claude-opus-5-5]（中转站按它支持的模型填）: " MODEL < /dev/tty
  # 去掉首尾空白；若误粘了多段文字，只取最后一段
  for v in APP_ID APP_SECRET API_KEY BASE_URL MODEL; do
    val=$(printf '%s' "${!v}" | awk '{print $NF}')
    printf -v "$v" '%s' "$val"
  done
  umask 077
  {
    printf 'export FEISHU_APP_ID=%q\n' "${APP_ID:-cli_aa365e8b88f91bef}"
    printf 'export FEISHU_APP_SECRET=%q\n' "$APP_SECRET"
    printf 'export ANTHROPIC_API_KEY=%q\n' "$API_KEY"
    printf 'export CLAUDE_MODEL=%q\n' "${MODEL:-claude-opus-5-5}"
    if [ -n "$BASE_URL" ]; then printf 'export ANTHROPIC_BASE_URL=%q\n' "${BASE_URL%/}"; fi
  } > .env
  echo "已保存到 $(pwd)/.env（填错了就删掉这个文件重新运行）"
fi

# Agent 配置（旧的 .env 没有这部分时补问）
if ! grep -q CLAUDE_MODE .env; then
  echo "== Agent 配置 =="
  read -r -p "Claude Code 的工作目录 [$HOME]: " WORKDIR < /dev/tty
  read -r -p "是否允许它执行任意终端命令？(y/N，选 N 则只能读写文件): " ALLOW_CMD < /dev/tty
  WORKDIR=$(printf '%s' "$WORKDIR" | awk '{$1=$1;print}')
  case "$ALLOW_CMD" in [yY]*) PERM=bypassPermissions ;; *) PERM=acceptEdits ;; esac
  {
    printf 'export CLAUDE_MODE=cli\n'
    printf 'export CLAUDE_WORKDIR=%q\n' "${WORKDIR:-$HOME}"
    printf 'export CLAUDE_PERMISSION_MODE=%q\n' "$PERM"
  } >> .env
fi

source .env
if [ "$CLAUDE_MODE" = cli ] && ! command -v claude >/dev/null; then
  echo "找不到 claude 命令。请先安装 Claude Code：curl -fsSL https://claude.ai/install.sh | bash"
  exit 1
fi
echo "== 自检 =="
.venv/bin/python check.py
echo "== 启动机器人（不要关闭此窗口，按 Ctrl+C 停止）=="
exec .venv/bin/python bot.py
