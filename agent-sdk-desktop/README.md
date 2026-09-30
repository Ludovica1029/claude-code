# 在本地桌面安装 Claude Agent SDK

这些脚本会在桌面上创建 `claude-agent-sdk` 文件夹，在里面建一个独立的 Python 虚拟环境，并安装 [Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/overview)（`claude-agent-sdk`）。macOS / Linux 的 Python 包自带 Claude Code CLI；**Windows 的包不带**，安装脚本会额外运行官方安装器 `irm https://claude.ai/install.ps1 | iex` 装好 `claude.exe`（SDK 在 Windows 上不接受 npm 装出来的 `claude.cmd`）。都不需要 Node.js。

## 前提条件

| 需要 | 说明 |
| --- | --- |
| Python 3.10+ | Windows：<https://www.python.org/downloads/>（安装时勾选 **Add python.exe to PATH**）；macOS：`brew install python@3.12`；Ubuntu：`sudo apt install python3 python3-venv` |
| Anthropic API Key | 在 <https://console.anthropic.com/> 创建，形如 `sk-ant-...` |

## 一键安装

先下载本仓库（或只下载 `agent-sdk-desktop` 文件夹），然后：

**Windows（PowerShell）**

```powershell
cd agent-sdk-desktop
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install-windows.ps1
```

**macOS / Linux**

```bash
cd agent-sdk-desktop
bash install-mac-linux.sh
```

安装完成后，桌面上会出现：

```
Desktop/claude-agent-sdk/
├── .venv/               # 独立的 Python 环境（已装好 SDK）
├── hello_agent.py       # 示例 agent
└── run-agent.bat        # Windows 双击运行（macOS/Linux 为 run-agent.command）
```

## 设置 API Key

```powershell
# Windows（永久生效，需重新打开终端）
setx ANTHROPIC_API_KEY "sk-ant-..."
```

```bash
# macOS / Linux（写入 ~/.zshrc 或 ~/.bashrc）
export ANTHROPIC_API_KEY="sk-ant-..."
```

不设置也可以：运行 `run-agent` 启动器时会提示你输入。

## 运行示例

- 双击桌面 `claude-agent-sdk` 文件夹中的 `run-agent.bat`（Windows）或 `run-agent.command`（macOS）
- 或在终端中：

```bash
cd ~/Desktop/claude-agent-sdk
./.venv/bin/python hello_agent.py "帮我总结这个文件夹里有什么"        # macOS / Linux
.venv\Scripts\python.exe hello_agent.py "帮我总结这个文件夹里有什么"   # Windows
```

## 手动安装（不用脚本）

```bash
mkdir ~/Desktop/claude-agent-sdk && cd ~/Desktop/claude-agent-sdk
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install claude-agent-sdk
```

如果更喜欢 TypeScript（需要 Node.js 18+）：

```bash
npm install @anthropic-ai/claude-agent-sdk
```

## 常见问题

- **`python` 不是内部或外部命令**：重装 Python 并勾选 “Add to PATH”，或改用 `py` 命令。
- **PowerShell 提示禁止运行脚本**：先执行 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`。
- **macOS 双击 `.command` 提示无法打开**：右键 → 打开，或在终端运行 `bash run-agent.command`。
- **Windows 报 `Claude Code not found`**：在 PowerShell 运行 `irm https://claude.ai/install.ps1 | iex`，然后重新打开终端。
- **认证错误 / 401**：检查 `ANTHROPIC_API_KEY` 是否正确、账户是否有余额。
- **升级 SDK**：`.venv/bin/python -m pip install -U claude-agent-sdk`。
