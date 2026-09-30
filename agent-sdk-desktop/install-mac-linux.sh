#!/usr/bin/env bash
# Install the Claude Agent SDK (Python) into a folder on the desktop (macOS / Linux).
# Usage: bash install-mac-linux.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP="$HOME/Desktop"
[ -d "$HOME/桌面" ] && [ ! -d "$DESKTOP" ] && DESKTOP="$HOME/桌面"
TARGET="$DESKTOP/claude-agent-sdk"

echo "==> 安装目录: $TARGET"

# 1. Python >= 3.10
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "未找到 python3。macOS: brew install python@3.12；Ubuntu: sudo apt install python3 python3-venv" >&2
  exit 1
fi
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "需要 Python 3.10+，当前为 $("$PYTHON" --version)" >&2
  exit 1
fi
echo "==> $("$PYTHON" --version)"

# 2. Create folder + virtualenv
mkdir -p "$TARGET"
"$PYTHON" -m venv "$TARGET/.venv"

# 3. Install the SDK
"$TARGET/.venv/bin/python" -m pip install --upgrade pip
"$TARGET/.venv/bin/python" -m pip install --upgrade claude-agent-sdk

# 4. Copy example + launcher
cp "$SCRIPT_DIR/hello_agent.py" "$TARGET/"
cat > "$TARGET/run-agent.command" <<'LAUNCHER'
#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  read -r -p "请输入 ANTHROPIC_API_KEY: " ANTHROPIC_API_KEY
  export ANTHROPIC_API_KEY
fi
./.venv/bin/python hello_agent.py "$@"
LAUNCHER
chmod +x "$TARGET/run-agent.command"

"$TARGET/.venv/bin/python" -c "import claude_agent_sdk; print('claude-agent-sdk', claude_agent_sdk.__version__, '安装成功')"
echo
echo "完成！双击桌面上 claude-agent-sdk/run-agent.command（或在终端运行）即可运行示例。"
echo "建议把 API Key 写入 ~/.zshrc 或 ~/.bashrc: export ANTHROPIC_API_KEY=\"sk-ant-...\""
