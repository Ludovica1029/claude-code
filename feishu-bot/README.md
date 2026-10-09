# 飞书 Claude 对话机器人

用长连接接收飞书消息，调用 Claude 回复，不需要公网 IP。

## 运行

```bash
cd feishu-bot
pip install -r requirements.txt
export FEISHU_APP_ID=cli_xxx FEISHU_APP_SECRET=xxx ANTHROPIC_API_KEY=sk-ant-xxx
python check.py   # 自检凭证和机器人能力
python bot.py     # 保持运行
```

`bot.py` 启动后，到飞书开放平台：

1. 事件与回调 → 订阅方式选「使用长连接接收事件」→ 保存（程序必须在运行中）
2. 添加事件 `im.message.receive_v1`
3. 权限：`im:message.p2p_msg:readonly`、`im:message.group_at_msg:readonly`、`im:message:send_as_bot`
4. 创建版本并发布

然后私聊机器人，或在群里 @ 它。发送 `/reset` 清空上下文。

默认是 Agent 模式（`CLAUDE_MODE=cli`），调用本机 `claude -p`，需先安装 Claude Code：`curl -fsSL https://claude.ai/install.sh | bash`。第一个给机器人发消息的人会被绑定为主人，其他人无法使用。

**不要把 App Secret 和 API Key 提交到仓库。**

## 群聊与访客

群里出现以下情况时，机器人会回复（需开通 `im:message.group_msg`）：
- 有人 @机器人
- 有人回复机器人发过的消息
- 消息里提到关键词：默认是机器人名字，可在 `.env` 里设置 `export FEISHU_BOT_KEYWORDS=小璐,小助手`

如果要回复群里的所有消息，设置 `export FEISHU_GROUP_REPLY=all`。

**主人**用完整的 Agent 模式。**其他人（访客）**用只读的受限模式：只能读 `~/digital-twin`（`GUEST_WORKDIR`）里的资料，不能改文件，也不能执行命令。要关闭访客功能，设置 `export FEISHU_ALLOW_GUESTS=0`。

首次启动时，`start.sh` 会用 `twin-template/` 生成 `~/digital-twin/CLAUDE.md`（数字分身的人设）和 `knowledge/`（资料目录）。
