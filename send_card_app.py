import streamlit as st
import requests
import json
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 从环境变量获取后端API地址
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:5000")
SEND_CARD_ENDPOINT = f"{BACKEND_API_URL}/send_card"

st.set_page_config(layout="wide")

st.title("飞书卡片发送工具")
st.markdown("--- ")

# --- Session State 初始化 ---
# 用于在多次交互之间保持用户输入的值
if 'app_id' not in st.session_state:
    st.session_state.app_id = ''
if 'app_secret' not in st.session_state:
    st.session_state.app_secret = ''
if 'chat_id' not in st.session_state:
    st.session_state.chat_id = ''
if 'card_title' not in st.session_state:
    st.session_state.card_title = ''
if 'card_json' not in st.session_state:
    st.session_state.card_json = '''
{
    "schema": "2.0",
    "header": {
        "title": {
            "tag": "plain_text",
            "content": ""
        }
    },
    "elements": []
}
'''

# --- 侧边栏：机器人配置 ---
st.sidebar.header("机器人配置")
st.session_state.app_id = st.sidebar.text_input(
    "App ID", 
    value=st.session_state.app_id, 
    help="在飞书开放平台 -> 凭证与基础信息中找到你的App ID"
)
st.session_state.app_secret = st.sidebar.text_input(
    "App Secret", 
    type="password", 
    value=st.session_state.app_secret,
    help="在飞书开放平台 -> 凭证与基础信息中找到你的App Secret"
)

st.sidebar.markdown("--- ")
st.sidebar.info("请确保你的机器人已经被邀请到目标群组中。")

# --- 主界面 --- #
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. 填写发送信息")
    st.session_state.chat_id = st.text_input(
        "接收群组的Chat ID", 
        value=st.session_state.chat_id, 
        help="如何获取Chat ID: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/chat/introduction#89c8a7c0"
    )
    st.session_state.card_title = st.text_input(
        "卡片标题 (用于后台追踪)", 
        value=st.session_state.card_title,
        help="这个标题将用于在数据库中记录和区分不同的卡片，不会显示在卡片上。"
    )

    st.subheader("2. 粘贴卡片 JSON")
    st.session_state.card_json = st.text_area(
        "从飞书卡片搭建工具导出的JSON", 
        height=500, 
        value=st.session_state.card_json
    )

with col2:
    st.subheader("3. 预览与发送")

    if st.button("发送卡片消息"):
        # --- 输入校验 ---
        if not all([st.session_state.app_id, st.session_state.app_secret, st.session_state.chat_id, st.session_state.card_title, st.session_state.card_json]):
            st.error("所有字段均为必填项，请检查输入！")
        else:
            try:
                # 尝试解析JSON以确保其格式正确
                card_content = json.loads(st.session_state.card_json)
                
                # 准备发送到后端API的数据
                payload = {
                    "app_id": st.session_state.app_id,
                    "app_secret": st.session_state.app_secret,
                    "chat_id": st.session_state.chat_id,
                    "card_title": st.session_state.card_title,
                    "card_json": card_content
                }

                with st.spinner('正在发送卡片...'):
                    response = requests.post(SEND_CARD_ENDPOINT, json=payload)
                    
                    if response.status_code == 200:
                        res_data = response.json()
                        if res_data.get("success"):
                            st.success(f"卡片发送成功！Message ID: {res_data.get('message_id')}")
                            st.info("卡片上下文已成功存入数据库。")
                        else:
                            st.error(f"后端API返回错误: {res_data.get('error')}")
                    else:
                        st.error(f"请求后端API失败，状态码: {response.status_code}")
                        st.code(response.text, language='text')

            except json.JSONDecodeError:
                st.error("卡片JSON格式无效，请从飞书卡片搭建工具重新复制。")
            except Exception as e:
                st.error(f"发生未知错误: {e}")

    st.markdown("--- ")
    st.subheader("实时预览")
    try:
        # 尝试渲染卡片预览
        card_to_preview = json.loads(st.session_state.card_json)
        st.json(card_to_preview)
    except:
        st.warning("JSON格式有误，无法生成预览。")