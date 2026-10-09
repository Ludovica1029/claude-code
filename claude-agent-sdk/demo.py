"""Claude Agent SDK 最小示例：让 agent 用 Bash 工具建文件。

  pip install -r requirements.txt
  真实模型：export ANTHROPIC_API_KEY=sk-ant-...  然后 python demo.py
  本地 mock： node mock_llm.mjs 8788 &  然后 MOCK=1 python demo.py
  MIN=1 只给模型暴露 Bash/Read 两个工具（请求体从 ~100KB 降到 ~17KB）。
"""
import os
import time
from pathlib import Path

import anyio
from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock,
                              ToolResultBlock, ToolUseBlock, UserMessage, query)

ws = Path(__file__).resolve().parent / "workspace"
ws.mkdir(exist_ok=True)
env = {"ANTHROPIC_BASE_URL": "http://127.0.0.1:8788", "ANTHROPIC_API_KEY": "fake",
       "NO_PROXY": "127.0.0.1"} if os.environ.get("MOCK") == "1" else {}

opts = ClaudeAgentOptions(
    cwd=str(ws),
    env=env,
    allowed_tools=["Bash", "Read", "Write", "Edit"],          # 免审批的工具
    tools=["Bash", "Read"] if os.environ.get("MIN") == "1" else None,  # 模型能看到的工具
    model="claude-sonnet-4-5" if env else None,
)


async def main():
    t0 = time.time()
    async for m in query(prompt="create out.txt with hello", options=opts):
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, ToolUseBlock):
                    print("tool_call:", b.name, b.input)
                elif isinstance(b, TextBlock):
                    print("text:", b.text)
        elif isinstance(m, UserMessage) and isinstance(m.content, list):
            for b in m.content:
                if isinstance(b, ToolResultBlock):
                    print("tool_result:", str(b.content)[:200])
        elif isinstance(m, ResultMessage):
            print("result:", m.subtype, m.result, "turns=", m.num_turns, "session=", m.session_id)
    print(f"elapsed {time.time() - t0:.2f}s")


anyio.run(main)
