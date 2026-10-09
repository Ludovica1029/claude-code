"""飞书 ↔ Claude 对话机器人（长连接模式，无需公网 IP）。

环境变量:
  FEISHU_APP_ID, FEISHU_APP_SECRET  飞书应用凭证
  ANTHROPIC_API_KEY                 Claude API Key
  CLAUDE_MODEL                      可选，默认 claude-opus-5-5
  CLAUDE_MODE                       可选，api（默认，纯对话）或 cli（调用本机 claude 命令，可读代码跑命令）
  CLAUDE_WORKDIR                    可选，cli 模式下 claude 的工作目录
"""
import json, logging, os, re, subprocess, threading
from collections import OrderedDict

import anthropic
import lark_oapi as lark
from lark_oapi.api.im.v1 import (P2ImMessageReceiveV1, ReplyMessageRequest,
                                 ReplyMessageRequestBody)

APP_ID = os.environ["FEISHU_APP_ID"]
APP_SECRET = os.environ["FEISHU_APP_SECRET"]
MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
MODE = os.environ.get("CLAUDE_MODE", "api")
WORKDIR = os.environ.get("CLAUDE_WORKDIR", os.getcwd())
MAX_TURNS = 20  # 每个会话保留的历史消息条数

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("feishu-bot")

feishu = lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build()
claude = anthropic.Anthropic() if MODE == "api" else None

history: dict[str, list] = {}
history_lock = threading.Lock()
seen: "OrderedDict[str, None]" = OrderedDict()  # 飞书可能重推同一事件，按 message_id 去重


def reply(message_id: str, text: str) -> None:
    req = (ReplyMessageRequest.builder().message_id(message_id)
           .request_body(ReplyMessageRequestBody.builder().msg_type("text")
                         .content(json.dumps({"text": text})).build())
           .build())
    resp = feishu.im.v1.message.reply(req)
    if not resp.success():
        log.error("回复失败 code=%s msg=%s", resp.code, resp.msg)


def ask_claude(chat_id: str, text: str) -> str:
    if text in ("/reset", "/清空"):
        with history_lock:
            history.pop(chat_id, None)
        return "已清空本会话的上下文。"

    if MODE == "cli":
        out = subprocess.run(["claude", "-p", text, "--output-format", "text"],
                             cwd=WORKDIR, capture_output=True, text=True, timeout=600)
        return out.stdout.strip() or out.stderr.strip() or "(无输出)"

    with history_lock:
        msgs = history.setdefault(chat_id, [])
        msgs.append({"role": "user", "content": text})
        del msgs[:-MAX_TURNS]
        # 历史必须以 user 开头
        while msgs and msgs[0]["role"] != "user":
            msgs.pop(0)
        snapshot = list(msgs)
    resp = claude.messages.create(model=MODEL, max_tokens=4096, messages=snapshot)
    answer = "".join(b.text for b in resp.content if b.type == "text")
    with history_lock:
        history[chat_id].append({"role": "assistant", "content": answer})
    return answer


def handle(msg) -> None:
    try:
        text = json.loads(msg.content).get("text", "")
        text = re.sub(r"@_user_\d+", "", text).strip()  # 去掉群聊 @机器人 占位符
        if not text:
            return
        log.info("收到 chat=%s: %s", msg.chat_id, text[:80])
        reply(msg.message_id, ask_claude(msg.chat_id, text))
    except Exception as e:
        log.exception("处理消息出错")
        reply(msg.message_id, f"出错了: {e}")


def on_message(data: P2ImMessageReceiveV1) -> None:
    msg = data.event.message
    if msg.message_id in seen:
        return
    seen[msg.message_id] = None
    if len(seen) > 1000:
        seen.popitem(last=False)
    if msg.message_type != "text":
        reply(msg.message_id, "目前只支持文字消息。")
        return
    # 飞书要求 3 秒内处理完事件，否则会重推，所以放到后台线程
    threading.Thread(target=handle, args=(msg,), daemon=True).start()


if __name__ == "__main__":
    handler = (lark.EventDispatcherHandler.builder("", "")
               .register_p2_im_message_receive_v1(on_message).build())
    log.info("启动长连接，模式=%s 模型=%s", MODE, MODEL)
    lark.ws.Client(APP_ID, APP_SECRET, event_handler=handler, log_level=lark.LogLevel.INFO).start()
