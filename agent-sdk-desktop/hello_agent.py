"""Minimal Claude Agent SDK example.

Usage:
    python hello_agent.py                       # default prompt
    python hello_agent.py "列出当前目录的文件"    # custom prompt
"""

import sys

import anyio
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query


async def main() -> None:
    prompt = " ".join(sys.argv[1:]) or "你好！请用一句话介绍你自己，并列出当前目录下的文件。"
    options = ClaudeAgentOptions(
        system_prompt="你是一个运行在用户桌面上的中文助手。",
        allowed_tools=["Read", "Glob", "Grep"],  # read-only tools; add "Write", "Bash" etc. as needed
        max_turns=5,
    )

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)
        elif isinstance(message, ResultMessage) and message.total_cost_usd is not None:
            print(f"\n[完成] 花费: ${message.total_cost_usd:.4f}")


if __name__ == "__main__":
    anyio.run(main)
