"""飞书 ↔ Claude 对话机器人（长连接模式，无需公网 IP）。

环境变量:
  FEISHU_APP_ID, FEISHU_APP_SECRET  飞书应用凭证
  ANTHROPIC_API_KEY                 Claude API Key（cli 模式下也会传给 claude 命令）
  ANTHROPIC_BASE_URL                可选，中转站地址
  CLAUDE_MODEL                      可选，默认 claude-opus-5-5
  CLAUDE_MODE                       cli（Agent：调用本机 Claude Code，可读写文件、跑命令）或 api（纯对话）
  CLAUDE_WORKDIR                    cli 模式下 Claude Code 的工作目录，默认用户主目录
  CLAUDE_PERMISSION_MODE            cli 模式下的权限：acceptEdits（默认，可改文件不能跑命令）
                                    或 bypassPermissions（可跑任何命令）
  FEISHU_OWNER_OPEN_IDS             可选，允许使用的飞书 open_id（逗号分隔）。
                                    不填则第一个发消息的人自动绑定为主人，记录在 .owner
"""
import json, logging, os, re, shutil, subprocess, threading
from collections import OrderedDict, defaultdict

import lark_oapi as lark
from lark_oapi.api.im.v1 import (P2ImMessageReceiveV1, ReplyMessageRequest,
                                 ReplyMessageRequestBody)

APP_ID = os.environ["FEISHU_APP_ID"]
APP_SECRET = os.environ["FEISHU_APP_SECRET"]
MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
MODE = os.environ.get("CLAUDE_MODE", "cli")
WORKDIR = os.path.expanduser(os.environ.get("CLAUDE_WORKDIR", "~"))
PERMISSION_MODE = os.environ.get("CLAUDE_PERMISSION_MODE", "acceptEdits")
CLI_TIMEOUT = 1800       # 单个任务最长 30 分钟
MAX_TURNS = 20           # api 模式每个会话保留的历史消息条数
MAX_REPLY = 15000        # 飞书单条消息别太长
OWNER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".owner")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("feishu-bot")

feishu = lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build()

if MODE == "api":
    import anthropic
    claude = anthropic.Anthropic()
else:
    CLAUDE_BIN = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    if not os.path.exists(CLAUDE_BIN):
        raise SystemExit("找不到 claude 命令，请先安装 Claude Code：curl -fsSL https://claude.ai/install.sh | bash")

state_lock = threading.Lock()
history: dict = {}                       # api 模式：chat_id -> 消息列表
sessions: dict = {}                      # cli 模式：chat_id -> Claude Code session_id
chat_locks = defaultdict(threading.Lock)  # 同一会话的消息按顺序处理
seen: "OrderedDict[str, None]" = OrderedDict()  # 飞书可能重推同一事件，按 message_id 去重


# ---------- 主人校验 ----------

def load_owners() -> set:
    ids = {x.strip() for x in os.environ.get("FEISHU_OWNER_OPEN_IDS", "").split(",") if x.strip()}
    if os.path.exists(OWNER_FILE):
        with open(OWNER_FILE) as f:
            ids |= {line.strip() for line in f if line.strip()}
    return ids


owners = load_owners()


def check_owner(open_id: str) -> str:
    """返回 'ok' / 'bound'（刚绑定）/ 'denied'。"""
    with state_lock:
        if open_id in owners:
            return "ok"
        if not owners:
            owners.add(open_id)
            with open(OWNER_FILE, "w") as f:
                f.write(open_id + "\n")
            os.chmod(OWNER_FILE, 0o600)
            log.info("已绑定主人 open_id=%s", open_id)
            return "bound"
    return "denied"


# ---------- 飞书 ----------

def reply(message_id: str, text: str) -> None:
    if len(text) > MAX_REPLY:
        text = text[:MAX_REPLY] + "\n\n…（内容过长已截断）"
    req = (ReplyMessageRequest.builder().message_id(message_id)
           .request_body(ReplyMessageRequestBody.builder().msg_type("text")
                         .content(json.dumps({"text": text})).build())
           .build())
    resp = feishu.im.v1.message.reply(req)
    if not resp.success():
        log.error("回复失败 code=%s msg=%s", resp.code, resp.msg)


# ---------- Claude ----------

def ask_api(chat_id: str, text: str) -> str:
    with state_lock:
        msgs = history.setdefault(chat_id, [])
        msgs.append({"role": "user", "content": text})
        del msgs[:-MAX_TURNS]
        while msgs and msgs[0]["role"] != "user":  # 历史必须以 user 开头
            msgs.pop(0)
        snapshot = list(msgs)
    resp = claude.messages.create(model=MODEL, max_tokens=4096, messages=snapshot)
    answer = "".join(b.text for b in resp.content if b.type == "text")
    with state_lock:
        history[chat_id].append({"role": "assistant", "content": answer})
    return answer


def ask_cli(chat_id: str, text: str) -> str:
    cmd = [CLAUDE_BIN, "-p", text, "--output-format", "json",
           "--permission-mode", PERMISSION_MODE, "--model", MODEL]
    sid = sessions.get(chat_id)
    if sid:
        cmd += ["--resume", sid]  # 接着上一轮对话
    out = subprocess.run(cmd, cwd=WORKDIR, capture_output=True, text=True,
                         timeout=CLI_TIMEOUT, stdin=subprocess.DEVNULL)
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        log.error("claude 输出无法解析 rc=%s stderr=%s", out.returncode, out.stderr[-2000:])
        return "Claude Code 运行出错：\n" + (out.stderr.strip() or out.stdout.strip() or f"退出码 {out.returncode}")[-3000:]
    if data.get("session_id"):
        sessions[chat_id] = data["session_id"]
    result = data.get("result") or "(无输出)"
    return ("⚠️ " + result) if data.get("is_error") else result


def ask_claude(chat_id: str, text: str) -> str:
    if text in ("/reset", "/清空", "/new"):
        with state_lock:
            history.pop(chat_id, None)
            sessions.pop(chat_id, None)
        return "已开始新对话。"
    return ask_cli(chat_id, text) if MODE == "cli" else ask_api(chat_id, text)


# ---------- 事件处理 ----------

def handle(msg) -> None:
    try:
        text = json.loads(msg.content).get("text", "")
        text = re.sub(r"@_user_\d+", "", text).strip()  # 去掉群聊 @机器人 占位符
        if not text:
            return
        log.info("收到 chat=%s: %s", msg.chat_id, text[:80])
        with chat_locks[msg.chat_id]:
            reply(msg.message_id, ask_claude(msg.chat_id, text))
    except subprocess.TimeoutExpired:
        reply(msg.message_id, f"任务超过 {CLI_TIMEOUT // 60} 分钟，已中止。")
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

    open_id = data.event.sender.sender_id.open_id
    status = check_owner(open_id)
    if status == "denied":
        log.warning("拒绝非主人 open_id=%s", open_id)
        reply(msg.message_id, "抱歉，这个机器人只供主人使用。")
        return
    if status == "bound":
        reply(msg.message_id, "已把你绑定为主人，之后只有你能使用这个机器人。")

    if msg.message_type != "text":
        reply(msg.message_id, "目前只支持文字消息。")
        return
    if MODE == "cli":
        reply(msg.message_id, "收到，处理中…")
    # 飞书要求 3 秒内处理完事件，否则会重推，所以放到后台线程
    threading.Thread(target=handle, args=(msg,), daemon=True).start()


if __name__ == "__main__":
    handler = (lark.EventDispatcherHandler.builder("", "")
               .register_p2_im_message_receive_v1(on_message).build())
    log.info("启动长连接，模式=%s 模型=%s 工作目录=%s 权限=%s", MODE, MODEL, WORKDIR, PERMISSION_MODE)
    if not owners:
        log.info("尚未绑定主人：第一个给机器人发消息的人会成为主人，请你自己先发")
    lark.ws.Client(APP_ID, APP_SECRET, event_handler=handler, log_level=lark.LogLevel.INFO).start()
