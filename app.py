import os
import re
import json
import requests
import threading
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

# --- 配置信息 ---
# 这些值将从部署平台的环境变量中读取
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

# --- Flask App 初始化 ---
app = Flask(__name__)

# --- 工具函数 ---

def get_feishu_tenant_access_token():
    """获取飞书 tenant_access_token"""
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

def get_steam_game_data(steam_url):
    """从 Steam 链接抓取游戏数据"""
    try:
        print(f">>> [Log] 开始抓取 Steam 页面: {steam_url}")
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
        print(">>> [Log] 成功抓取 Steam 数据")

        return {
            "title": title,
            "short_desc": short_desc,
            "tags": tags[:10],
            "full_desc": full_desc[:2000] # 可以适当加长描述
        }
    except Exception as e:
        print(f"!!! [Error] 抓取 Steam 数据失败: {e}")
        return None

def call_deepseek_ai(game_data):
    """调用 DeepSeek AI 进行分析"""
    print(">>> [Log] 正在调用 DeepSeek AI...")
    prompt = f"""
    你是一位资深的游戏评测家。请根据以下 Steam 游戏信息，进行全面分析并打分。

    **游戏名称**: {game_data['title']}
    **游戏标签**: {', '.join(game_data['tags'])}
    **简短介绍**: 
    {game_data['short_desc']}
    **详细介绍**:
    {game_data['full_desc']}

    **你的任务**:
    1.  **核心玩法总结**: 用2-3句话总结游戏的核心玩法和特色。
    2.  **优点分析**: 列出这款游戏可能的2-3个优点。
    3.  **缺点分析**: 列出这款游戏可能的2-3个缺点。
    4.  **好玩指数**: 综合以上信息，给出一个1-10分的好玩指数（请给出整数），并用一句话解释为什么给这个分数。

    请严格按照以下格式输出，使用 Markdown 语法：
    ### 核心玩法
    [这里是你的总结]

    ### 亮点 ✨
    - [优点1]
    - [优点2]

    ### 槽点 ⛈️
    - [缺点1]
    - [缺点2]

    ### 好玩指数
    **[分数]/10** - [你的打分理由]
    """
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一位资深的游戏评测家。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 1024
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        data = response.json()
        print(">>> [Log] 成功获取 DeepSeek AI 分析结果")
        return data['choices'][0]['message']['content']
    except Exception as e:
        print(f"!!! [Error] 调用 DeepSeek API 失败: {e}")
        return "抱歉，AI 分析服务暂时出了一点小问题..."

def reply_feishu_message(message_id, content, title="🎮 Steam 游戏分析报告"):
    """回复消息卡片到飞书"""
    print(">>> [Log] 准备回复飞书消息...")
    token = get_feishu_tenant_access_token()
    if not token: 
        print("!!! [Error] 因 token 获取失败，无法回复消息")
        return
        
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }
    card_content = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": title}
        },
        "elements": [{"tag": "markdown", "content": content}]
    }
    payload = { "msg_type": "interactive", "content": json.dumps(card_content) }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        print(f">>> [Log] 成功发送飞书消息: {response.json().get('msg')}")
    except Exception as e:
        print(f"!!! [Error] 发送飞书消息失败: {e}")

def process_game_analysis(steam_url, message_id):
    """实际处理游戏分析的后台线程任务"""
    print("--- [Log] 后台线程开始执行分析 ---")
    game_data = get_steam_game_data(steam_url)
    if not game_data:
        reply_feishu_message(message_id, f"哎呀，无法从这个链接获取游戏信息，请检查链接是否正确或稍后再试。\n{steam_url}", "处理失败")
        return
    ai_summary = call_deepseek_ai(game_data)
    final_content = f"**{game_data['title']}**\n\n" + ai_summary + f"\n\n[前往 Steam 商店页面]({steam_url})"
    reply_feishu_message(message_id, final_content, f"🎮 {game_data['title']} 分析报告")
    print("--- [Log] 后台线程执行完毕 ---")

@app.route("/feishu/event", methods=["POST"])
def feishu_event_handler():
    """接收飞书事件的主入口"""
    data = request.json
    print(f"\n---------- [Log] 收到新请求: {data.get('header', {}).get('event_type')} ----------")

    # 1. 处理 URL 验证请求
    if "challenge" in data:
        print(">>> [Log] 正在处理 URL 验证...")
        return jsonify({"challenge": data["challenge"]})

    # 2. 处理事件回调
    event = data.get("event")
    if not event:
        print(">>> [Log] 请求中无 event 字段，忽略。")
        return jsonify({"status": "error"})

    message = event.get("message")
    if not message:
        print(">>> [Log] event 中无 message 字段，忽略。")
        return jsonify({"status": "ignored"})
    
    # 3. 判断是否为群聊中的@消息
    chat_type = message.get("chat_type")
    if chat_type != "group":
        print(f">>> [Log] 非群聊消息 ({chat_type})，忽略。")
        return jsonify({"status": "ignored"})
        
    # 4. 尝试从消息中提取文本和Steam链接
    try:
        content = json.loads(message.get("content", "{}"))
        text_content = content.get("text", "")
        match = re.search(r'(https://store\.steampowered\.com/app/\d+)', text_content)
        
        if match:
            steam_url = match.group(1)
            message_id = message.get("message_id")
            print(f">>> [Log] 成功匹配到 Steam 链接: {steam_url}")
            
            # 启动后台线程进行耗时操作，避免飞书超时
            thread = threading.Thread(target=process_game_analysis, args=(steam_url, message_id))
            thread.start()
            
            print(">>> [Log] 已启动后台线程进行分析，立即返回。")
            return jsonify({"status": "processing"})
        else:
            print(">>> [Log] 消息中未匹配到 Steam 链接，忽略。")
    
    except Exception as e:
        print(f"!!! [Error] 处理消息时发生严重错误: {e}")

    # 5. 对于所有不满足条件的情况，都返回成功，避免飞书重试
    return jsonify({"status": "ok"})

# Serverless 平台会自动处理启动，所以这里的 if __name__ ... 不会执行，但保留它是个好习惯
if __name__ == "__main__":
    # 仅用于本地测试，端口可以随意设置
    app.run(host="0.0.0.0", port=8080, debug=True)