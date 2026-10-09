"""以你本人身份读取飞书文档的 MCP 工具，补上官方 lark-mcp 读不了的「内嵌电子表格」。

只用 Python 标准库。两种用法:
  python feishu_docs_mcp.py login   在浏览器里授权一次（重定向 URL 需配置为 http://localhost:3000/callback）
  python feishu_docs_mcp.py         作为 MCP 服务运行（由 Claude Code 启动）

提供的工具（全部只读）:
  read_feishu_doc   读取文档/知识库/电子表格链接的完整内容，文档里嵌的电子表格会展开成表格文本
  read_sheet        读取某个电子表格（或其中一张工作表、某个区域）的单元格

环境变量: FEISHU_APP_ID, FEISHU_APP_SECRET
令牌保存在 ~/.config/feishu-bot/user_token.json（仅本人可读）。
"""
import http.server
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

BASE = "https://open.feishu.cn"
REDIRECT_URI = "http://localhost:3000/callback"
SCOPES = "offline_access docx:document:readonly wiki:wiki:readonly sheets:spreadsheet:readonly"
TOKEN_FILE = os.path.expanduser("~/.config/feishu-bot/user_token.json")
MAX_ROWS = 300   # 每张工作表最多读多少行
MAX_COLS = 40

APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")


class FeishuError(Exception):
    pass


# ---------- HTTP ----------

def http_json(method, path, body=None, token=None, query=None):
    url = BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            data = json.load(e)
        except Exception:
            raise FeishuError(f"HTTP {e.code} {path}")
    if data.get("code", 0) != 0:
        raise FeishuError(f"{path} 失败: code={data.get('code')} msg={data.get('msg') or data.get('error_description')}")
    return data


# ---------- 用户令牌 ----------

def save_token(tok):
    now = int(time.time())
    data = {
        "access_token": tok["access_token"],
        "expires_at": now + int(tok.get("expires_in", 7200)) - 120,
        "refresh_token": tok.get("refresh_token", ""),
        "refresh_expires_at": now + int(tok.get("refresh_token_expires_in", 0)),
        "scope": tok.get("scope", ""),
    }
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    return data


def user_token():
    if not os.path.exists(TOKEN_FILE):
        raise FeishuError("还没有授权，请在终端运行: python feishu_docs_mcp.py login")
    with open(TOKEN_FILE) as f:
        data = json.load(f)
    if time.time() < data["expires_at"]:
        return data["access_token"]
    if not data.get("refresh_token"):
        raise FeishuError("授权已过期，请在终端重新运行: python feishu_docs_mcp.py login")
    tok = http_json("POST", "/open-apis/authen/v2/oauth/token", {
        "grant_type": "refresh_token", "client_id": APP_ID, "client_secret": APP_SECRET,
        "refresh_token": data["refresh_token"]})
    return save_token(tok)["access_token"]


def login():
    state = secrets.token_urlsafe(16)
    url = BASE + "/open-apis/authen/v1/authorize?" + urllib.parse.urlencode({
        "client_id": APP_ID, "response_type": "code", "redirect_uri": REDIRECT_URI,
        "scope": SCOPES, "state": state})
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state and q.get("code"):
                result["code"] = q["code"][0]
                msg = "授权成功，可以关闭此页面并回到终端。"
            else:
                result.setdefault("error", q.get("error", ["未知错误"])[0])
                msg = "授权失败：" + result["error"]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h3>{msg}</h3>".encode())

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 3000), Handler)
    server.timeout = 180
    print("请在浏览器中完成飞书授权（若没自动打开，复制下面的链接到浏览器）：\n" + url, flush=True)
    webbrowser.open(url)
    deadline = time.time() + 180
    while "code" not in result and "error" not in result and time.time() < deadline:
        server.handle_request()
    server.server_close()
    if "code" not in result:
        sys.exit("授权未完成：" + result.get("error", "超时"))
    tok = http_json("POST", "/open-apis/authen/v2/oauth/token", {
        "grant_type": "authorization_code", "client_id": APP_ID, "client_secret": APP_SECRET,
        "code": result["code"], "redirect_uri": REDIRECT_URI})
    data = save_token(tok)
    print("✅ 授权成功，已保存到", TOKEN_FILE)
    if not data["refresh_token"]:
        print("⚠️ 没有拿到 refresh_token，授权约 2 小时后过期。请确认应用已开通 offline_access 权限。")


# ---------- 电子表格 ----------

def col_letter(n):
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def cell_text(v):
    if v is None:
        return ""
    if isinstance(v, list):
        return "".join(cell_text(x) for x in v)
    if isinstance(v, dict):
        return str(v.get("text") or v.get("link") or v.get("name") or "")
    return str(v).replace("\n", " ")


def list_sheets(ss_token, token):
    data = http_json("GET", f"/open-apis/sheets/v3/spreadsheets/{ss_token}/sheets/query", token=token)
    return data.get("data", {}).get("sheets", [])


def read_sheet(ss_token, sheet_id="", cell_range="", token=None):
    token = token or user_token()
    if "_" in ss_token and not sheet_id:  # 文档里内嵌表格的 token 形如 <表格token>_<sheet_id>
        ss_token, sheet_id = ss_token.rsplit("_", 1)
    sheets = list_sheets(ss_token, token)
    if sheet_id:
        sheets = [s for s in sheets if s.get("sheet_id") == sheet_id] or [{"sheet_id": sheet_id}]
    out = []
    for s in sheets:
        sid = s["sheet_id"]
        grid = s.get("grid_properties") or {}
        rows = min(int(grid.get("row_count") or MAX_ROWS), MAX_ROWS)
        cols = min(int(grid.get("column_count") or 26), MAX_COLS)
        rng = f"{sid}!{cell_range}" if cell_range else f"{sid}!A1:{col_letter(cols)}{rows}"
        data = http_json("GET", f"/open-apis/sheets/v2/spreadsheets/{ss_token}/values/{urllib.parse.quote(rng, safe='!:')}",
                         token=token, query={"valueRenderOption": "ToString",
                                             "dateTimeRenderOption": "FormattedString"})
        values = data.get("data", {}).get("valueRange", {}).get("values") or []
        lines = ["\t".join(cell_text(c) for c in row).rstrip() for row in values]
        while lines and not lines[-1].strip():
            lines.pop()
        title = s.get("title") or sid
        out.append(f"【工作表：{title}（{sid}）】\n" + ("\n".join(lines) if lines else "（空）"))
        if int(grid.get("row_count") or 0) > MAX_ROWS:
            out.append(f"（只读取了前 {MAX_ROWS} 行，可用 read_sheet 指定 range 继续读）")
    return "\n\n".join(out)


# ---------- 文档 ----------

def block_text(block):
    for v in block.values():
        if isinstance(v, dict) and isinstance(v.get("elements"), list):
            parts = []
            for el in v["elements"]:
                for key in ("text_run", "mention_doc", "mention_user", "equation"):
                    if key in el:
                        parts.append(el[key].get("content") or el[key].get("title") or "")
            return "".join(parts)
    return ""


HEADING = {3: "# ", 4: "## ", 5: "### ", 6: "#### ", 7: "##### ", 8: "###### "}


def read_docx(doc_id, token):
    blocks, page = [], None
    while True:
        q = {"page_size": 500, "document_revision_id": -1}
        if page:
            q["page_token"] = page
        data = http_json("GET", f"/open-apis/docx/v1/documents/{doc_id}/blocks", token=token, query=q).get("data", {})
        blocks += data.get("items", [])
        if not data.get("has_more"):
            break
        page = data.get("page_token")
    out = []
    for b in blocks:
        t = b.get("block_type")
        if t == 30:  # 内嵌电子表格
            st = (b.get("sheet") or {}).get("token", "")
            try:
                out.append(read_sheet(st, token=token))
            except FeishuError as e:
                out.append(f"（内嵌电子表格 {st} 读取失败：{e}）")
        elif t == 18:
            out.append(f"（此处是多维表格 {(b.get('bitable') or {}).get('token', '')}，请用多维表格工具读取）")
        elif t == 27:
            out.append("（图片）")
        else:
            text = block_text(b)
            if text.strip():
                prefix = HEADING.get(t, "- " if t in (12, 13) else "")
                out.append(prefix + text)
    return "\n".join(out)


def read_feishu_doc(url):
    token = user_token()
    m = re.search(r"/(wiki|docx|docs|sheets|base)/([A-Za-z0-9]+)", url)
    if not m:
        kind, obj = "docx", url.strip()
    else:
        kind, obj = m.groups()
    if kind == "wiki":
        node = http_json("GET", "/open-apis/wiki/v2/spaces/get_node", token=token,
                         query={"token": obj}).get("data", {}).get("node", {})
        kind, obj = node.get("obj_type", "docx"), node.get("obj_token", obj)
        header = f"标题：{node.get('title', '')}\n\n"
    else:
        header = ""
    if kind == "sheet" or kind == "sheets":
        return header + read_sheet(obj, token=token)
    if kind == "docx":
        return header + read_docx(obj, token)
    raise FeishuError(f"暂不支持读取这种类型：{kind}")


# ---------- MCP（stdio, JSON-RPC）----------

TOOLS = [
    {
        "name": "read_feishu_doc",
        "description": "以主人身份读取飞书文档的完整内容（支持 docx 文档、知识库 wiki、电子表格链接）。"
                       "文档里内嵌的电子表格会被展开成制表符分隔的表格文本。读飞书文档时优先用这个工具。",
        "inputSchema": {"type": "object", "properties": {
            "url": {"type": "string", "description": "飞书文档链接，或 docx 的 document_id"}},
            "required": ["url"]},
    },
    {
        "name": "read_sheet",
        "description": "读取飞书电子表格的单元格。token 可以是电子表格 token，也可以是文档内嵌表格的 "
                       "<表格token>_<sheet_id> 形式；可选 sheet_id 和 range（如 A1:H100）。",
        "inputSchema": {"type": "object", "properties": {
            "token": {"type": "string"},
            "sheet_id": {"type": "string"},
            "range": {"type": "string", "description": "如 A1:H100，不填则读整张表"}},
            "required": ["token"]},
    },
]


def call_tool(name, args):
    if name == "read_feishu_doc":
        return read_feishu_doc(args["url"])
    if name == "read_sheet":
        return read_sheet(args["token"], args.get("sheet_id", ""), args.get("range", ""))
    raise FeishuError("未知工具: " + name)


def serve():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if mid is None:  # 通知，不需要回复
            continue
        if method == "initialize":
            result = {"protocolVersion": params.get("protocolVersion", "2024-11-05"),
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "feishu-docs", "version": "1.0.0"}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                text, err = call_tool(params.get("name"), params.get("arguments") or {}), False
            except Exception as e:
                text, err = f"出错：{e}", True
            result = {"content": [{"type": "text", "text": text}], "isError": err}
        elif method == "ping":
            result = {}
        else:
            reply = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "Method not found"}}
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    if not APP_ID or not APP_SECRET:
        sys.exit("请先设置环境变量 FEISHU_APP_ID 和 FEISHU_APP_SECRET（source .env）")
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        login()
    else:
        serve()
