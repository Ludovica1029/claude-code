# DeepSeek Harness（dsh）本地运行

DeepSeek 2026-08 开源的 agent harness，MIT 协议，“一切皆插件”（基于 Cordis）。本目录固定 `@deepseek-ai/dsh@0.2.0-rc.2`（开发者预览版，会有破坏性变更）。需要 Node.js ≥ 22.19。

## 三种用法

| 用法 | 命令 | 适合 |
|---|---|---|
| Web UI | `npx dsh web` → http://127.0.0.1:3080 | 交互式写代码 |
| Headless（一次性任务） | `./run_headless.sh "任务"` | 脚本、CI |
| SDK（JSON-RPC over stdio） | `python sdk_demo.py`（说明见文件头） | 嵌入自己的程序 |

## 运行

```sh
npm install
export DEEPSEEK_API_KEY=sk-...          # 真实模型
./run_headless.sh "列出当前目录的文件"

MOCK=1 ./run_headless.sh                # 不需要 key：用本地 mock 模型走完整工具调用循环
```

- `DSH_HOME` 默认设成本目录下的 `.dsh-home`，会话、配置都存在里面，不碰 `~/.dsh`。
- 换模型：dsh 自带 `llm-pi-ai` 适配器，可在 profile 的 `cordis.patch.yml` 里配置 OpenAI / Anthropic / 任意 OpenAI 兼容网关（见上游 `packages/llm/llm-pi-ai/README.zh.md`）。
- `npx dsh headless --dump-config` 可以看到组成 headless 的 96 个插件条目，每一个都能用 patch 替换。

## mock_llm.mjs

一个最小的 Anthropic Messages 兼容服务器（DeepSeek 官方端点 `api.deepseek.com/anthropic` 用的就是这个协议）。它会让模型调用一次 shell 工具，收到结果后回答 `DONE`，并把每个请求的结构（工具数、system 长度、字节数）记到 `mock-requests.jsonl`。只用来验证 harness 本身，不代表模型能力。
