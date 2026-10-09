# Claude Agent SDK 本地运行

Anthropic 官方的 agent SDK（Python `claude-agent-sdk` / TypeScript `@anthropic-ai/claude-agent-sdk`），底层就是 Claude Code 的运行时：SDK 启动内置的 `claude` CLI 子进程，通过流式 JSON 通信。本目录固定 Python 版 `0.2.165`。

## 运行

```sh
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...     # 真实模型（也支持 Bedrock / Vertex 等）
python demo.py

node mock_llm.mjs 8788 &                # 不需要 key：本地 mock 模型
MOCK=1 python demo.py
MOCK=1 MIN=1 python demo.py             # 只暴露 Bash/Read 两个工具
```

## 要点

- `allowed_tools` 是“免审批”名单；`tools` 才决定模型能看到哪些工具。默认会暴露 27 个内置工具，第一次请求约 100KB；`tools=["Bash","Read"]` 后约 17KB。
- 非交互环境里，不在 `allowed_tools` 里的工具调用会被拒绝（或者用 `permission_mode` / `can_use_tool` 回调自己决定）。
- 内置能力：hooks、subagents、MCP 服务器（含进程内 `@tool`）、会话恢复（`resume`）、skills、`CLAUDE.md` 等，跟 Claude Code 一致。
- 它会读取 `~/.claude` 和项目 `.claude/` 里的配置；要完全隔离就设 `setting_sources` 或换 `HOME` / `CLAUDE_CONFIG_DIR`。

## mock_llm.mjs

同 `../deepseek-harness/mock_llm.mjs`：最小的 Anthropic Messages 兼容服务器，只用来验证 SDK 的工具循环和请求结构。
