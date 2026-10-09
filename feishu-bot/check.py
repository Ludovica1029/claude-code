"""自检：验证飞书应用凭证是否有效、机器人能力是否已启用。只读，不发送消息。

用法: FEISHU_APP_ID=... FEISHU_APP_SECRET=... python check.py
"""
import json, os, sys, urllib.request

BASE = "https://open.feishu.cn/open-apis"


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def main():
    app_id, secret = os.environ.get("FEISHU_APP_ID"), os.environ.get("FEISHU_APP_SECRET")
    if not app_id or not secret:
        sys.exit("请先设置环境变量 FEISHU_APP_ID 和 FEISHU_APP_SECRET")

    tok = call("POST", "/auth/v3/tenant_access_token/internal", {"app_id": app_id, "app_secret": secret})
    if tok.get("code") != 0:
        sys.exit(f"[失败] 凭证无效: code={tok.get('code')} msg={tok.get('msg')}")
    print("[通过] App ID / App Secret 有效")

    bot = call("GET", "/bot/v3/info", token=tok["tenant_access_token"])
    if bot.get("code") != 0:
        sys.exit(f"[失败] 读取机器人信息失败: code={bot.get('code')} msg={bot.get('msg')}\n"
                 "      → 检查是否添加了「机器人」能力并发布了版本")
    info = bot.get("bot", {})
    print(f"[通过] 机器人: {info.get('app_name')}  状态: "
          f"{'已启用' if info.get('activate_status') == 2 else info.get('activate_status')}")


if __name__ == "__main__":
    main()
