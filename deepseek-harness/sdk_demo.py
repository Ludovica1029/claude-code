"""用 dsh 的 Python SDK（JSON-RPC over stdio）驱动 Harness，跑两轮对话。

PyPI 上还没有和 0.2.x 运行时配套的 deepseek-harness-sdk，所以这里直接用仓库源码：
  git clone --depth 1 https://github.com/deepseek-ai/deepseek-harness ../_dsh-src
  pip install "pydantic>=2.12,<3"
  PYTHONPATH=../_dsh-src/python/sdk/src python sdk_demo.py
真实模型：设置 DEEPSEEK_API_KEY；本地 mock：先 `node mock_llm.mjs 8787` 再加 MOCK=1。
"""
import os
import time
from pathlib import Path

from deepseek_harness import DeepSeekHarness

here = Path(__file__).resolve().parent
ws = here / "workspace"
ws.mkdir(exist_ok=True)
mock = os.environ.get("MOCK") == "1"

t0 = time.time()
with DeepSeekHarness(
    dsh_bin=str(here / "node_modules/.bin/dsh"),  # 先 npm install
    dsh_home=str(here / ".dsh-home"),
    cwd=str(ws),
    provider="deepseek-official",
    model="deepseek-flash",
    base_url="http://127.0.0.1:8787" if mock else None,
    api_key="fake" if mock else None,
) as h:
    r = h.run("create out.txt with hello")
    print("final:", r.final_response, "| session:", r.session_id, "| events:", len(r.events))
    print("event types:", sorted({e.get("type") for e in r.events}))
    r2 = h.run("now append world", session_id=r.session_id)  # 同一 session 继续
    print("turn2:", r2.final_response, f"| total {time.time() - t0:.2f}s")
