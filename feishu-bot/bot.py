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
  FEISHU_GROUP_REPLY                群聊里何时回复：mention（默认，@机器人、回复机器人的消息、
                                    或包含关键词时才回复）或 all（回复所有消息）
  FEISHU_BOT_KEYWORDS               可选，群消息里出现这些词（逗号分隔）也算在问机器人，
                                    默认是机器人名字。需开通「获取群组中所有消息」权限
  FEISHU_ALLOW_GUESTS               其他人能否使用，默认 1。访客走只读的受限模式：
                                    只能读 GUEST_WORKDIR 里的资料，不能改文件、不能跑命令
  GUEST_WORKDIR                     访客模式的资料目录，默认 ~/digital-twin
"""
import json, logging, os, re, shutil, subprocess, threading
from collections import OrderedDict, defaultdict

import lark_oapi as lark
from lark_oapi.api.im.v1 import (GetMessageRequest, P2ImMessageReceiveV1,
                                 ReplyMessageRequest, ReplyMessageRequestBody)

APP_ID = os.environ["FEISHU_APP_ID"]
APP_SECRET = os.environ["FEISHU_APP_SECRET"]
MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
MODE = os.environ.get("CLAUDE_MODE", "cli")
WORKDIR = os.path.expanduser(os.environ.get("CLAUDE_WORKDIR", "~"))
PERMISSION_MODE = os.environ.get("CLAUDE_PERMISSION_MODE", "acceptEdits")
GROUP_REPLY = os.environ.get("FEISHU_GROUP_REPLY", "mention")
ALLOW_GUESTS = os.environ.get("FEISHU_ALLOW_GUESTS", "1") not in ("0", "false", "no", "")
GUEST_WORKDIR = os.path.expanduser(os.environ.get("GUEST_WORKDIR", "~/digital-twin"))
GUEST_PROMPT = (
    "你正在飞书里替主人回答同事的问题，提问的人不是主人本人。"
    "你只能根据当前目录里的资料（先看 CLAUDE.md 和 knowledge/）和常识回答。"
    "不要编造主人的安排、承诺或决定；拿不准、涉及隐私或需要主人拍板的事，"
    "就回答「这个需要主人本人确认」。回答要简洁。"
)
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


def fetch_bot_info() -> dict:
    """机器人自己的 open_id 和名字，用来判断群消息是不是在问它。"""
    try:
        req = (lark.BaseRequest.builder().http_method(lark.HttpMethod.GET)
               .uri("/open-apis/bot/v3/info").token_types({lark.AccessTokenType.TENANT}).build())
        resp = feishu.request(req)
        return json.loads(resp.raw.content).get("bot", {})
    except Exception:
        log.exception("获取机器人信息失败，群聊中只要有 @ 就当作 @ 了机器人")
        return {}


_bot = fetch_bot_info()
BOT_OPEN_ID = _bot.get("open_id", "")
KEYWORDS = [k.strip() for k in os.environ.get("FEISHU_BOT_KEYWORDS", _bot.get("app_name", "")).split(",")
            if k.strip()]


def mentions_bot(msg) -> bool:
    mentions = msg.mentions or []
    if not BOT_OPEN_ID:
        return bool(mentions)
    return any(m.id and m.id.open_id == BOT_OPEN_ID for m in mentions)


def replies_to_bot(msg) -> bool:
    """这条消息是不是在回复机器人发过的消息。"""
    if not msg.parent_id:
        return False
    try:
        resp = feishu.im.v1.message.get(GetMessageRequest.builder().message_id(msg.parent_id).build())
        items = (resp.data.items if resp.success() and resp.data else None) or []
        return bool(items) and items[0].sender.sender_type == "app"
    except Exception:
        log.exception("查询被回复的消息失败")
        return False


def is_asking_bot(msg, text: str) -> bool:
    if GROUP_REPLY == "all" or mentions_bot(msg):
        return True
    if any(k.lower() in text.lower() for k in KEYWORDS):
        return True
    return replies_to_bot(msg)


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


def ask_cli(key: str, text: str, guest: bool = False) -> str:
    cmd = [CLAUDE_BIN, "-p", text, "--output-format", "json", "--model", MODEL]
    if guest:
        # 访客：只读、只能看资料目录，不能改文件、不能跑命令
        cmd += ["--permission-mode", "default", "--tools", "Read,Glob,Grep",
                "--restricted", "--strict-mcp-config", "--append-system-prompt", GUEST_PROMPT]
        cwd = GUEST_WORKDIR
    else:
        cmd += ["--permission-mode", PERMISSION_MODE]
        cwd = WORKDIR
    sid = sessions.get(key)
    if sid:
        cmd += ["--resume", sid]  # 接着上一轮对话
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                         timeout=CLI_TIMEOUT, stdin=subprocess.DEVNULL)
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        log.error("claude 输出无法解析 rc=%s stderr=%s", out.returncode, out.stderr[-2000:])
        return "Claude Code 运行出错：\n" + (out.stderr.strip() or out.stdout.strip() or f"退出码 {out.returncode}")[-3000:]
    if data.get("session_id"):
        sessions[key] = data["session_id"]
    result = data.get("result") or "(无输出)"
    return ("⚠️ " + result) if data.get("is_error") else result


def ask_claude(chat_id: str, text: str, guest: bool) -> str:
    key = chat_id + (":guest" if guest else "")  # 访客和主人的上下文分开
    if text in ("/reset", "/清空", "/new"):
        with state_lock:
            history.pop(key, None)
            sessions.pop(key, None)
        return "已开始新对话。"
    if guest:
        return ask_cli(key, text, guest=True) if MODE == "cli" else ask_api(key, "[同事提问] " + text)
    return ask_cli(key, text) if MODE == "cli" else ask_api(key, text)


# ---------- 事件处理 ----------

def clean_text(msg) -> str:
    text = json.loads(msg.content).get("text", "")
    return re.sub(r"@_user_\d+", "", text).strip()  # 去掉 @ 占位符


def handle(msg, guest: bool) -> None:
    try:
        text = clean_text(msg)
        if not text:
            return
        log.info("收到 chat=%s %s: %s", msg.chat_id, "访客" if guest else "主人", text[:80])
        key = msg.chat_id + (":guest" if guest else "")
        with chat_locks[key]:
            reply(msg.message_id, ask_claude(msg.chat_id, text, guest))
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

    # 飞书要求 3 秒内处理完事件，否则会重推，所以判断和处理都放到后台线程
    threading.Thread(target=dispatch, args=(data,), daemon=True).start()


def dispatch(data: P2ImMessageReceiveV1) -> None:
    try:
        _dispatch(data)
    except Exception:
        log.exception("分发消息出错")


def _dispatch(data: P2ImMessageReceiveV1) -> None:
    msg = data.event.message
    is_group = msg.chat_type != "p2p"
    if is_group:
        text = clean_text(msg) if msg.message_type == "text" else ""
        if not is_asking_bot(msg, text):
            return  # 群里不是在问机器人的消息不理会

    open_id = data.event.sender.sender_id.open_id
    status = check_owner(open_id)
    guest = status == "denied"
    if guest and not ALLOW_GUESTS:
        log.warning("拒绝非主人 open_id=%s", open_id)
        if not is_group:  # 群里不回拒绝消息，免得刷屏
            reply(msg.message_id, "抱歉，这个机器人只供主人使用。")
        return
    if status == "bound":
        reply(msg.message_id, "已把你绑定为主人。其他人也可以问我，但只能查资料，不能操作你的电脑。")

    if msg.message_type != "text":
        reply(msg.message_id, "目前只支持文字消息。")
        return
    if MODE == "cli":
        reply(msg.message_id, "收到，处理中…")
    handle(msg, guest)


if __name__ == "__main__":
    handler = (lark.EventDispatcherHandler.builder("", "")
               .register_p2_im_message_receive_v1(on_message).build())
    os.makedirs(os.path.join(GUEST_WORKDIR, "knowledge"), exist_ok=True)
    log.info("启动长连接，模式=%s 模型=%s 工作目录=%s 权限=%s 群聊=%s 关键词=%s 访客=%s(%s)",
             MODE, MODEL, WORKDIR, PERMISSION_MODE, GROUP_REPLY, KEYWORDS,
             "开" if ALLOW_GUESTS else "关", GUEST_WORKDIR)
    if not owners:
        log.info("尚未绑定主人：第一个给机器人发消息的人会成为主人，请你自己先发")
    lark.ws.Client(APP_ID, APP_SECRET, event_handler=handler, log_level=lark.LogLevel.INFO).start()
