#!/usr/bin/env bash
# 一键启动：首次运行会建虚拟环境、装依赖、询问密钥并保存到 .env，之后直接启动。
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "== 创建虚拟环境并安装依赖 =="
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

if [ ! -f .env ]; then
  echo "== 首次配置（输入内容不会显示，粘贴后直接回车）=="
  read -r -p "飞书 App ID [cli_aa365e8b88f91bef]: " APP_ID < /dev/tty
  read -r -s -p "飞书 App Secret: " APP_SECRET < /dev/tty; echo
  read -r -s -p "Claude API Key (sk-ant-...): " API_KEY < /dev/tty; echo
  umask 077
  cat > .env <<ENV
export FEISHU_APP_ID=${APP_ID:-cli_aa365e8b88f91bef}
export FEISHU_APP_SECRET=$APP_SECRET
export ANTHROPIC_API_KEY=$API_KEY
ENV
  echo "已保存到 $(pwd)/.env（填错了就删掉这个文件重新运行）"
fi

source .env
echo "== 自检 =="
.venv/bin/python check.py
echo "== 启动机器人（不要关闭此窗口，按 Ctrl+C 停止）=="
exec .venv/bin/python bot.py
