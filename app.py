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
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# --- Gemini API 配置 ---
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    print(">>> [Log] Gemini API 已成功配置")
else:
    print("!!! [Warning] 未找到 GOOGLE_API_KEY 环境变量，AI 功能将无法使用")

# --- 全局变量和缓存 ---
_BOT_OPEN_ID = None # 用于缓存机器人的 open_id，避免每次请求都重新获取

# --- Flask App 初始化 ---
app = Flask(__name__)

# --- 通用工具函数 ---
def get_feishu_tenant_access_token():
    """
    获取飞书 tenant_access_token。
    此 token 用于调用飞书开放平台 API。
    """
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    payload = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status() # 对 4xx/5xx 响应抛出异常
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

def get_bot_open_id():
    """
    获取并缓存飞书机器人的 open_id。
    这个 ID 在处理群聊 @ 消息时用于识别机器人自身。
    """
    global _BOT_OPEN_ID
    if _BOT_OPEN_ID: # 如果已缓存，直接返回
        return _BOT_OPEN_ID

    token = get_feishu_tenant_access_token()
    if not token:
        print("!!! [Error] 因 token 获取失败，无法获取 Bot Open ID")
        return None

    # 调用飞书接口获取机器人信息
    url = "https://open.feishu.cn/open-apis/bot/v3/info"
    headers = { "Authorization": f"Bearer {token}" }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        # 修改：从 'data' 字段改为 'bot' 字段访问 open_id，这是根据上次您提供的错误信息调整的
        if data.get("code") == 0 and data.get("bot", {}).get("open_id"):
            _BOT_OPEN_ID = data["bot"]["open_id"]
            print(f">>> [Log] 成功获取 Bot Open ID: {_BOT_OPEN_ID}")
            return _BOT_OPEN_ID
        else:
            print(f"!!! [Error] 获取 Bot Open ID 失败或数据格式不符: {data}") 
            return None
    except requests.exceptions.RequestException as e:
        print(f"!!! [Error] 请求 Bot Info 异常: {e}")
        return None

def reply_feishu_message(message_id, content, title="🎮 Steam 游戏分析报告"):
    """
    回复飞书消息，使用互动卡片格式。
    """
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
    """
    从 Steam 商店页面抓取游戏数据。
    """
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
        
        # 提取游戏信息
        title = soup.find('div', class_='apphub_AppName').text.strip() if soup.find('div', class_='apphub_AppName') else "未知游戏"
        short_desc = soup.find('div', class_='game_description_snippet').text.strip() if soup.find('div', class_='game_description_snippet') else "无简短介绍"
        tags = [tag.text.strip() for tag in soup.find_all('a', class_='app_tag')] if soup.find_all('a', class_='app_tag') else []
        full_desc_element = soup.find('div', id='game_area_description')
        full_desc = full_desc_element.get_text(separator='\n', strip=True) if full_desc_element else "无详细介绍"
        
        print(">>> [Log] [游戏模式] 成功抓取 Steam 数据")
        return {"title": title, "short_desc": short_desc, "tags": tags[:10], "full_desc": full_desc[:2000]}
    except Exception as e:
        print(f"!!! [Error] [游戏模式] 抓取 Steam 数据失败: {e}")
        return None

# --- “游戏评测大师” (Gemini版) ---

def call_gemini_for_game_review(game_data):
    """【Gemini版】调用 Gemini Pro (或 Flash) 进行游戏分析"""
    print(">>> [Log] [游戏模式] 正在调用 Gemini API (评测大师模式)...")
    model = genai.GenerativeModel('gemini-2.5-flash') # 使用最新的 gemini-2.5-flash 模型
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
    """
    后台线程处理游戏分析请求。
    """
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
    """【Gemini版】调用 Gemini Pro (或 Flash) 回答通用问题"""
    print(">>> [Log] [通用模式] 正在调用 Gemini API (通用助手模式)...")
    model = genai.GenerativeModel('gemini-2.5-flash') # 使用最新的 gemini-2.5-flash 模型
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
    """
    后台线程处理通用聊天请求。
    """
    print("--- [Log] [通用模式] 后台线程启动 ---")
    ai_response = call_gemini_for_general_chat(user_question)
    reply_feishu_message(message_id, ai_response, "🤖 AI 助手 (Gemini)")
    print("--- [Log] [通用模式] 后台线程执行完毕 ---")

# --- 主入口与路由 ---

@app.route("/feishu/event", methods=["POST"])
def feishu_event_handler():
    """
    飞书事件回调处理主函数。
    负责接收飞书消息，并根据消息类型和内容分发处理。
    """
    data = request.json
    print(f"\n---------- [Log] 收到新请求: {data.get('header', {}).get('event_type')} ----------")
    # !!! DEBUG 打印：打印完整的接收到的飞书请求数据，用于排查 @ 消息问题
    print(f">>> [DEBUG] 完整请求数据: {json.dumps(data, indent=2, ensure_ascii=False)}") 

    # 处理飞书 URL 验证请求
    if "challenge" in data:
        print(">>> [Log] 正在处理 URL 验证...")
        return jsonify({"challenge": data["challenge"]})

    event = data.get("event")
    # 忽略非消息事件
    if not (event and event.get("message")):
        return jsonify({"status": "ignored", "reason": "No message event"})

    message = event.get("message")
    chat_type = message.get("chat_type")
    mentions = message.get("mentions", [])
    message_id = message.get("message_id")

    # 获取机器人的 open_id，用于判断是否 @ 了机器人
    bot_open_id = get_bot_open_id()
    if not bot_open_id:
        print("!!! [Error] 无法获取 Bot Open ID，无法精确过滤群聊/话题消息。请检查 FEISHU_APP_ID/SECRET 和网络。")
        # 即使无法获取机器人ID，P2P消息依然可以处理，但群聊过滤会受影响。
        # 这里不立即返回 ignored，而是让P2P消息继续，群聊消息则会在下面逻辑中因bot_open_id缺失而被跳过
        pass

    should_process = False

    if chat_type == "p2p": # 私聊消息，机器人总是回复
        should_process = True
        print(">>> [Log] P2P 消息，直接处理。")
    elif (chat_type == "group" or chat_type == "topic") and bot_open_id: # 群聊或话题消息，且成功获取了机器人ID
        # 遍历所有 @ 提及，看是否 @ 到了本机器人
        for mention in mentions:
            # 飞书的 mentions 结构中，id_type 和 id 是关键
            if mention.get('id_type') == 'open_id' and mention.get('id') == bot_open_id:
                should_process = True
                print(">>> [Log] 群聊/话题消息，且明确 @了机器人，准备处理。")
                break
        if not should_process: # 如果是群聊/话题消息但没有 @ 机器人，则忽略
            print(">>> [Log] 群聊/话题消息，但未明确 @机器人，忽略。")
    elif (chat_type == "group" or chat_type == "topic") and not bot_open_id:
        # 如果是群聊/话题消息但无法获取机器人ID，则出于安全考虑暂时忽略这类消息
        print("!!! [Warning] 无法获取 Bot Open ID，群聊/话题消息过滤失效，此消息暂时忽略。")
        return jsonify({"status": "ignored", "reason": "Bot ID not available for group filtering"})
    else: # 其他不支持的聊天类型，忽略
        print(f">>> [Log] 不支持的聊天类型 ({chat_type})，忽略。")
    
    # 只有当 should_process 为 True 时才进行后续处理
    if should_process:
        try:
            content = json.loads(message.get("content", "{}"))
            text_content = content.get("text", "").strip()
            
            # 移除所有 @ 提及的内容，以便 AI 专注于用户提出的问题/内容
            # 这里需要注意，如果 @ 的文本是可变的，或者有多种格式，这个替换可能不完全。
            # 更健壮的方法是解析 content 字段中的 "text" 部分，它通常是纯净的用户输入。
            # 但目前先根据 mentions 移除 @ 的文本。
            for mention in mentions:
                # 仅移除 @ 本机器人的文本，防止误伤用户 @ 其他人的内容
                if bot_open_id and mention.get('id_type') == 'open_id' and mention.get('id') == bot_open_id:
                     # 确保替换的是完整的 @提及文本
                     mention_text_pattern = re.escape(mention.get('text', ''))
                     text_content = re.sub(r'' + mention_text_pattern, '', text_content).strip()
                     # 如果飞书返回的 text_content 格式是 "<at open_id=\"ou_xxxx\">@机器人名称</at> 你好"
                     # 那么上面的替换可能不够，需要直接从 content 结构中提取非 @ 部分
                     # 但我们先尝试这个，因为更常见的是纯文本中包含 @ 字符串。
                
            user_question = text_content.strip()

            # 如果移除 @ 后消息内容为空（例如，用户只 @ 了一下机器人没说别的），则忽略
            if not user_question:
                print(">>> [Log] 移除 @ 后消息内容为空，忽略。")
                return jsonify({"status": "ignored", "reason": "Empty message after stripping mentions"})

            # 判断消息是否包含 Steam 链接
            match = re.search(r'(https://store\.steampowered\.com/app/\d+)', user_question)
            
            if match:
                print(">>> [Log] 检测到 Steam 链接，进入游戏评测模式")
                steam_url = match.group(0)
                # 在后台线程中处理游戏分析，避免阻塞主请求
                thread = threading.Thread(target=process_game_analysis, args=(steam_url, message_id))
                thread.start()
            elif user_question:
                print(">>> [Log] 未检测到链接，进入通用助手模式")
                # 在后台线程中处理通用聊天，避免阻塞主请求
                thread = threading.Thread(target=process_general_chat, args=(user_question, message_id))
                thread.start()

        except Exception as e:
            print(f"!!! [Error] 处理消息时发生严重错误: {e}")

    return jsonify({"status": "ok"}) # 无论是否回复，都返回 200 OK 给飞书，避免重试

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
