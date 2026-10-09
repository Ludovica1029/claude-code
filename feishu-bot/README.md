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

`CLAUDE_MODE=cli` 时改为调用本机 `claude -p`（需已安装并登录 Claude Code），可以让它在 `CLAUDE_WORKDIR` 下读代码、跑命令。

**不要把 App Secret 和 API Key 提交到仓库。**
