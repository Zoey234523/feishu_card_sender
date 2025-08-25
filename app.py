import os
import json
import requests
from flask import Flask, request, jsonify
from redis import Redis
from rq import Queue
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# --- 初始化 ---
app = Flask(__name__)

# Redis 和 RQ 初始化
redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
q = Queue(connection=redis_conn)

# --- 常量 ---
FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
TENANT_ACCESS_TOKEN_URI = "/auth/v3/tenant_access_token/internal"
SEND_MESSAGE_URI = "/im/v1/messages"

# --- 辅助函数：获取 Tenant Access Token ---
# 注意：在生产环境中，应该缓存此token，并处理其过期时间
def get_tenant_access_token(app_id, app_secret):
    """获取租户访问凭证"""
    url = f"{FEISHU_API_BASE}{TENANT_ACCESS_TOKEN_URI}"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    payload = {"app_id": app_id, "app_secret": app_secret}
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("code") == 0:
            return data.get("tenant_access_token"), None
        else:
            return None, f"获取token失败: {data.get('msg')}"
    except requests.RequestException as e:
        return None, f"请求飞书API异常: {e}"

# --- 核心API路由 ---

@app.route("/send_card", methods=["POST"])
def send_card():
    """
    接收前端请求，发送卡片，并将 message_id 与 card_title 关联存储在 Redis 中。
    """
    data = request.json
    app_id = data.get("app_id")
    app_secret = data.get("app_secret")
    chat_id = data.get("chat_id")
    card_title = data.get("card_title")
    card_json = data.get("card_json")

    if not all([app_id, app_secret, chat_id, card_title, card_json]):
        return jsonify({"success": False, "error": "缺少必要参数"}), 400

    # 1. 获取 Tenant Access Token
    token, error = get_tenant_access_token(app_id, app_secret)
    if error:
        return jsonify({"success": False, "error": error}), 500

    # 2. 发送卡片消息
    url = f"{FEISHU_API_BASE}{SEND_MESSAGE_URI}?receive_id_type=chat_id"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        "receive_id": chat_id,
        "msg_type": "interactive",
        "content": json.dumps(card_json),
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        res_data = response.json()

        if res_data.get("code") == 0:
            message_id = res_data.get("data", {}).get("message_id")
            if message_id:
                # 3. 在 Redis 中存储 message_id 和 card_title 的映射关系
                # key: "card_context:{message_id}", value: card_title
                # 设置过期时间，例如7天，防止Redis被无用数据填满
                redis_conn.set(f"card_context:{message_id}", card_title, ex=604800) # 7 days
                return jsonify({"success": True, "message_id": message_id})
            else:
                return jsonify({"success": False, "error": "未能从飞书返回数据中获取 message_id"}), 500
        else:
            return jsonify({"success": False, "error": f"发送卡片失败: {res_data.get('msg')}"}), 500

    except requests.RequestException as e:
        return jsonify({"success": False, "error": f"请求飞书API异常: {e}"}), 500


@app.route("/callback", methods=["POST"])
def callback():
    """
    接收飞书卡片交互的回调，并将任务推送到RQ队列。
    """
    data = request.json
    
    # 飞书开放平台要求对challenge请求进行特殊处理
    if data.get("type") == "url_verification":
        return jsonify({"challenge": data.get("challenge")})

    # 从回调数据中获取 message_id
    message_id = data.get("event", {}).get("message", {}).get("message_id")
    
    if not message_id:
        # 如果没有message_id，我们无法追踪上下文，可以选择忽略或记录一个错误
        print("Warning: Received a callback without a message_id.")
        return jsonify({"status": "ignored", "reason": "no message_id"})

    # 从 Redis 中获取 card_title
    card_title_bytes = redis_conn.get(f"card_context:{message_id}")
    card_title = card_title_bytes.decode('utf-8') if card_title_bytes else "Unknown"

    # 准备要传递给后台任务的数据
    job_data = {
        "card_title": card_title,
        "raw_interaction": data # 原始交互数据
    }

    # 将任务放入队列，由 worker.py 来处理
    q.enqueue("worker.save_interaction_to_db", job_data)

    # 立即返回成功响应给飞书
    return jsonify({"status": "success"})

if __name__ == "__main__":
    # 在生产环境中，应使用 Gunicorn 或 uWSGI 等WSGI服务器
    app.run(debug=True, port=5000)