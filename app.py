import os
import re
import json
import requests
import threading
import google.generativeai as genai
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

# --- 配置信息 ---
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET")
# 【V2 新增】使用 Google Gemini API Key
GOOGLE_API_KEY = os.environ.get("AIzaSyBFo6dLz18GJIIYEJyCMR4U_rvCgMwHJ28")

# --- Gemini API 配置 ---
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    print(">>> [Log] Gemini API 已成功配置")
else:
    print("!!! [Warning] 未找到 GOOGLE_API_KEY 环境变量，AI 功能将无法使用")

# --- Flask App 初始化 ---
app = Flask(__name__)

# --- 通用工具函数 (与之前版本相同) ---
def get_feishu_tenant_access_token():
    # ... 此函数内容与之前完全相同，为了简洁此处省略 ...
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    payload = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("code") == 0:
            print(">>> [Log] 成功获取 tenant_access_token")
            return data.get("tenant_access_token")
        else:
            print(f"!!! [Error] 获取飞书 token 失败: {data}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"!!! [Error] 请求飞书 token 异常: {e}")
        return None

def reply_feishu_message(message_id, content, title="🎮 Steam 游戏分析报告"):
    # ... 此函数内容与之前完全相同，为了简洁此处省略 ...
    print(">>> [Log] 准备回复飞书消息...")
    token = get_feishu_tenant_access_token()
    if not token: 
        print("!!! [Error] 因 token 获取失败，无法回复消息")
        return
        
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
    headers = { "Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8" }
    card_content = {
        "config": {"wide_screen_mode": True},
        "header": { "template": "blue", "title": {"tag": "plain_text", "content": title} },
        "elements": [{"tag": "markdown", "content": content}]
    }
    payload = { "msg_type": "interactive", "content": json.dumps(card_content) }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        print(f">>> [Log] 成功发送飞书消息: {response.json().get('msg')}")
    except Exception as e:
        print(f"!!! [Error] 发送飞书消息失败: {e}")

def get_steam_game_data(steam_url):
    # ... 此函数内容与之前完全相同，为了简洁此处省略 ...
    try:
        print(f">>> [Log] [游戏模式] 开始抓取 Steam 页面: {steam_url}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cookie': 'birthtime=568022401; lastagecheckage=1-January-1990; wants_mature_content=1'
        }
        response = requests.get(steam_url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.find('div', class_='apphub_AppName').text.strip()
        short_desc = soup.find('div', class_='game_description_snippet').text.strip()
        tags = [tag.text.strip() for tag in soup.find_all('a', class_='app_tag')]
        full_desc = soup.find('div', id='game_area_description').get_text(separator='\n', strip=True)
        print(">>> [Log] [游戏模式] 成功抓取 Steam 数据")
        return {"title": title, "short_desc": short_desc, "tags": tags[:10], "full_desc": full_desc[:2000]}
    except Exception as e:
        print(f"!!! [Error] [游戏模式] 抓取 Steam 数据失败: {e}")
        return None

# --- “游戏评测大师” (Gemini版) ---

def call_gemini_for_game_review(game_data):
    """【Gemini版】调用 Gemini Pro 进行游戏分析"""
    print(">>> [Log] [游戏模式] 正在调用 Gemini API (评测大师模式)...")
    model = genai.GenerativeModel('gemini-pro')
    prompt = f"""
    你是一位顶级的游戏行业分析师和资深评测家。请根据以下 Steam 游戏信息，进行深入、全面、专业的分析。

    **游戏名称**: {game_data['title']}
    **游戏标签**: {', '.join(game_data['tags'])}
    **简短介绍**: 
    {game_data['short_desc']}
    **详细介绍**:
    {game_data['full_desc']}

    **你的任务 (请严格按点回复)**:
    1.  **核心玩法**: 用2-3句话总结游戏的核心玩法与特色。
    2.  **亮点 ✨**: 列出这款游戏最吸引人的2-3个优点。
    3.  **槽点 ⛈️**: 列出这款游戏可能存在的2-3个缺点或风险。
    4.  **目标用户与竞品**: 
        - 根据标签和介绍，分析这款游戏主要的目标用户群体是谁？
        - 在当前市场上，有哪些知名的同类竞品？简单对比一下它们的质量和特色。
    5.  **同类游戏市场分析**: 
        - 综合来看，这款游戏所属的品类在Steam上的总体受欢迎程度如何？
        - 玩家对这类游戏通常有哪些期待？
    6.  **好玩指数**: 综合以上所有信息，给出一个1-10分的好玩指数（请给出整数），并用一句话解释打分理由。

    请严格按照以下格式输出，使用 Markdown 语法。
    """
    try:
        response = model.generate_content(prompt)
        # 检查是否有因安全原因被拦截
        if response.prompt_feedback.block_reason:
            reason = response.prompt_feedback.block_reason
            print(f"!!! [Error] [Gemini] Blocked due to safety reasons: {reason}")
            return f"抱歉，我的分析被安全规则拦截了，原因：{reason}。请换个游戏试试。"
            
        print(">>> [Log] [游戏模式] 成功获取 Gemini AI 分析结果")
        return response.text
    except Exception as e:
        print(f"!!! [Error] [游戏模式] 调用 Gemini API 失败: {e}")
        return "抱歉，Gemini 大脑暂时出了一点小问题..."

def process_game_analysis(steam_url, message_id):
    print("--- [Log] [游戏模式] 后台线程启动 ---")
    game_data = get_steam_game_data(steam_url)
    if not game_data:
        reply_feishu_message(message_id, f"哎呀，无法从这个链接获取游戏信息，请检查链接是否正确或稍后再试。\n{steam_url}", "处理失败")
        return
    ai_summary = call_gemini_for_game_review(game_data)
    final_content = f"**{game_data['title']}**\n\n" + ai_summary + f"\n\n[前往 Steam 商店页面]({steam_url})"
    reply_feishu_message(message_id, final_content, f"🎮 {game_data['title']} 分析报告")
    print("--- [Log] [游戏模式] 后台线程执行完毕 ---")

# --- “通用AI助手” (Gemini版) ---

def call_gemini_for_general_chat(user_question):
    """【Gemini版】调用 Gemini Pro 回答通用问题"""
    print(">>> [Log] [通用模式] 正在调用 Gemini API (通用助手模式)...")
    model = genai.GenerativeModel('gemini-pro')
    prompt = f"你是一个乐于助人、知识渊博的通用人工智能助手。请回答以下问题：\n\n{user_question}"
    try:
        response = model.generate_content(prompt)
        if response.prompt_feedback.block_reason:
            reason = response.prompt_feedback.block_reason
            print(f"!!! [Error] [Gemini] Blocked due to safety reasons: {reason}")
            return f"抱歉，我的回答被安全规则拦截了，原因：{reason}。请换个问题试试。"

        print(">>> [Log] [通用模式] 成功获取 Gemini AI 回答")
        return response.text
    except Exception as e:
        print(f"!!! [Error] [通用模式] 调用 Gemini API 失败: {e}")
        return "抱歉，我的 Gemini 大脑暂时出了一点小问题，请稍后再试。"

def process_general_chat(user_question, message_id):
    print("--- [Log] [通用模式] 后台线程启动 ---")
    ai_response = call_gemini_for_general_chat(user_question)
    reply_feishu_message(message_id, ai_response, "🤖 AI 助手 (Gemini)")
    print("--- [Log] [通用模式] 后台线程执行完毕 ---")

# --- 主入口与路由 (与之前版本相同) ---

@app.route("/feishu/event", methods=["POST"])
def feishu_event_handler():
    # ... 此函数内容与之前完全相同，为了简洁此处省略 ...
    data = request.json
    print(f"\n---------- [Log] 收到新请求: {data.get('header', {}).get('event_type')} ----------")

    if "challenge" in data:
        print(">>> [Log] 正在处理 URL 验证...")
        return jsonify({"challenge": data["challenge"]})

    event = data.get("event")
    if not (event and event.get("message")):
        return jsonify({"status": "ignored"})

    message = event.get("message")
    chat_type = message.get("chat_type")
    mentions = message.get("mentions", [])
    message_id = message.get("message_id")

    is_group_at_message = (chat_type == "group" and len(mentions) > 0)
    is_p2p_message = (chat_type == "p2p")
    is_topic_at_message = (chat_type == "topic" and len(mentions) > 0)

    if is_group_at_message or is_p2p_message or is_topic_at_message:
        try:
            content = json.loads(message.get("content", "{}"))
            text_content = content.get("text", "").strip()
            for mention in mentions:
                text_content = text_content.replace(mention.get('text', ''), '')
            user_question = text_content.strip()

            match = re.search(r'(https://store\.steampowered\.com/app/\d+)', user_question)
            
            if match:
                print(">>> [Log] 检测到 Steam 链接，进入游戏评测模式")
                steam_url = match.group(0)
                thread = threading.Thread(target=process_game_analysis, args=(steam_url, message_id))
                thread.start()
            elif user_question:
                print(">>> [Log] 未检测到链接，进入通用助手模式")
                thread = threading.Thread(target=process_general_chat, args=(user_question, message_id))
                thread.start()
            else:
                 print(">>> [Log] 消息为空，忽略。")

        except Exception as e:
            print(f"!!! [Error] 处理消息时发生严重错误: {e}")

    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
