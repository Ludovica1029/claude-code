# DeepSeek Harness vs Claude Agent SDK

测试时间 2026-10-09，Linux 容器，Node 22 / Python 3.13。版本：`@deepseek-ai/dsh@0.2.0-rc.2`（源码 `5badb15`），`claude-agent-sdk==0.2.165`（Python）/ `@anthropic-ai/claude-agent-sdk@0.3.295`（npm）。

两边各自的可运行示例在 [`deepseek-harness/`](deepseek-harness/) 和 [`claude-agent-sdk/`](claude-agent-sdk/)。

## 怎么测的

环境里没有 DeepSeek / Anthropic 的 API key，所以没有测模型效果。两个框架都说 Anthropic Messages 协议（DeepSeek 官方端点就是 `api.deepseek.com/anthropic`），于是用同一个本地 mock 服务器（`mock_llm.mjs`）当模型：第一步让模型调用 shell 工具执行 `echo hello > out.txt`，拿到工具结果后回答 `DONE`。这样比较的是 **harness 本身**：能不能跑通工具循环、启动开销、每次请求发给模型什么。

两边都跑通了：shell 工具真的执行了，`out.txt` 内容是 `hello`，最后的回答也正确返回。

## 实测数据

| | DeepSeek Harness | Claude Agent SDK |
|---|---|---|
| 安装 | npm 59s，`node_modules` 518MB | pip 10s，243MB（内置 `claude` 二进制）；npm 8s，301MB |
| 一次性任务（2 步，mock） | headless CLI 1.7–1.9s；Python SDK 首轮 1.4s，同进程第二轮 0.04s | 0.8–1.1s（干净环境，3 次） |
| 默认暴露给模型的工具 | 24 个（bash/read/write/edit/grep/glob/subagent/workflow/goal/todo/web…） | 27 个（Bash/Read/Write/Edit/Agent/Task*/Cron*/Monitor/Workflow/Web*…） |
| 第一次请求体 | ~53KB（工具 schema 19KB，system 2.6K 字符） | ~100KB（工具 schema 94KB）；`tools=["Bash","Read"]` 后 17KB |
| 附加请求 | 1 次生成会话标题（max_tokens 64） | 1 次无工具的辅助请求 |
| 默认 thinking / 输出上限 | 开启；deepseek-flash `max_tokens` 256000 | 开启，budget 31999；`max_tokens` 32000 |
| 工具权限默认值 | headless 下 bash 直接执行，没有拦截 | 不在 `allowed_tools` 里的工具会被拒绝 |
| 工具参数校验 | 缺必填字段时把错误作为 tool_result 返回给模型 | 同样有 schema 校验 |
| 会话持久化 | `$DSH_HOME/sessions` 下的只追加事件日志（JSONL），可按 id 恢复 / fork | `~/.claude/projects` 下的 JSONL，可 `resume` / fork |

注意：耗时里没有真实模型的延迟，只能说明框架开销都在 1–2 秒内，实际使用时会被模型延迟盖过。请求体大小会直接变成 token 成本：Claude SDK 默认工具集偏大，生产环境建议用 `tools=` 裁剪。

## 架构差异

**DeepSeek Harness：框架。** 基于 Cordis，模型适配器、工具、会话日志、审批策略，甚至 agent loop 本身都是插件。运行时是一棵由 profile + 有序 YAML patch 组成的插件树（`dsh headless --dump-config` 能看到 96 个条目）。同一个运行时可以用多种形态运行：Web UI、headless、SDK（JSON-RPC over stdio，有 TS/Python 客户端）、ACP、Electron 桌面。模型层通过 `llm-pi-ai` 支持 OpenAI、Anthropic 和任意兼容网关。

**Claude Agent SDK：产品级运行时的编程接口。** 就是把 Claude Code 封装成库：SDK 启动内置 CLI，用流式 JSON 通信。扩展点是有限且稳定的：hooks、自定义工具（进程内 MCP）、subagents、skills、权限回调、system prompt。agent loop 本身不能替换。

## 优劣

### DeepSeek Harness

优点
- MIT 开源，所有代码可读可改，loop、上下文压缩、工具管线都能替换，适合做 agent 研究或自研产品底座。
- 不绑定模型：DeepSeek 原生支持，另外可通过 pi-ai 接 OpenAI / Anthropic / 自建 vLLM 等。
- 一次组装多种形态（Web / CLI / SDK / ACP / 桌面），并且自带 Web UI。
- 默认请求更精简（第一次请求约为 Claude SDK 默认值的一半）。
- 文档详尽，中英双语。

缺点
- 开发者预览版（rc / alpha），README 明确说会有破坏性变更；npm 上的 `dsh-sdk-client` 停在 0.0.1-rc.1，Python SDK 也还没有和 0.2.x 配套的 PyPI 包，本次是直接用仓库源码跑的。
- 依赖重：518MB，安装 1 分钟；概念多（profile、bundle、patch、seam），上手成本高。
- headless 下 bash 默认直接执行，在自动化里跑之前要自己配沙箱或审批策略（见上游 `SAFETY.md`）。
- 发布才两个月，生态和生产案例都少。

### Claude Agent SDK

优点
- 成熟稳定，跟 Claude Code 同一个运行时，工具、上下文管理、压缩都经过大规模使用。
- 上手快：pip/npm 一个包，`query()` 几行就能跑；Python 和 TS 都是一等公民。
- 安全默认值更保守：工具需要显式放行，还有权限模式和 `can_use_tool` 回调。
- 与 Claude 模型配合最好（prompt caching、thinking、Bedrock/Vertex 部署）。

缺点
- 主要为 Claude 设计；`ANTHROPIC_BASE_URL` 理论上能接兼容网关（比如 DeepSeek 的 `/anthropic` 端点），但不是官方支持的路径，本次也没有用真实 key 验证。
- 运行时闭源（受 Anthropic 商业条款约束），agent loop 不能替换，只能用给定的扩展点定制。
- 默认工具集大，第一次请求约 100KB，需要用 `tools=` 裁剪。
- 会读取 `~/.claude` 和环境变量里的配置：本次在云容器里第一次跑时，就因为继承了宿主的环境变量多出了 39 个工具；嵌入别的产品时要注意隔离（`setting_sources`、`env`、`HOME`）。

## 怎么选

| 场景 | 推荐 |
|---|---|
| 用 Claude 模型、想最快做出可靠的生产 agent（代码审查机器人、CI 修复、内部工具） | Claude Agent SDK |
| 需要 Python/TS 稳定 API，团队不想维护 agent 框架本身 | Claude Agent SDK |
| 主要用 DeepSeek 模型，或者要在多家模型 / 自部署模型之间切换 | DeepSeek Harness |
| 要改 agent loop、上下文策略、工具管线，做研究或自研 agent 产品 | DeepSeek Harness |
| 需要现成的自托管 Web UI / 桌面端，并且能接受预览版的变动 | DeepSeek Harness |
| 对许可证有要求（必须完全开源可审计） | DeepSeek Harness |

一句话：**Claude Agent SDK 是“拿来就用的成熟运行时”，DeepSeek Harness 是“可以拆开重组的开源框架”**。现阶段做生产选前者；要模型自由度或深度定制，并且能承受 API 变动，选后者。

## 没测到的部分

- 真实模型下的任务完成率、token 成本、速度：需要 API key。把 key 填上以后，两个目录的 demo 不加 `MOCK=1` 就能直接跑。
- dsh 的 Web UI、ACP、桌面端，以及 Claude SDK 的 TypeScript 版只做了安装，没有跑任务。
