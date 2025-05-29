# coding: utf-8
import os
import logging
import sqlite3
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from sklearn.linear_model import LogisticRegression
from geopy.distance import geodesic
import gradio as gr
from flask import Flask, request
from linebot.v3.webhook import WebhookHandler
from linebot.v3.webhook import WebhookHandler, MessageEvent, TextMessageContent
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import QuickReply, QuickReplyButton, MessageAction

# 設定日誌
logging.basicConfig(level=logging.INFO)

# 載入 .env 檔案中的環境變數
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# 初始化 LINE Bot
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("LINE_CHANNEL_SECRET")

if not channel_access_token or not channel_secret:
    logging.error("缺少必要的環境變數：LINE_CHANNEL_ACCESS_TOKEN 或 LINE_CHANNEL_SECRET")
    raise ValueError("請設定 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 環境變數")

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

# 使用者狀態暫存
user_states = {}

# 初始化 SQLite 資料庫
def init_db():
    try:
        conn = sqlite3.connect("rides.db")
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS ride_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                origin TEXT,
                destination TEXT,
                ride_type TEXT,
                time TEXT,
                payment TEXT,
                origin_lat REAL,
                origin_lon REAL,
                dest_lat REAL,
                dest_lon REAL
            )
        """)
        conn.commit()
    except Exception as e:
        logging.error(f"初始化資料庫失敗: {e}")
    finally:
        conn.close()

init_db()

# 簡單的經緯度查找（模擬）
def get_coordinates(location):
    location_map = {
        "台北車站": (25.0478, 121.5170),
        "松山機場": (25.0634, 121.5520),
        "台大": (25.0169, 121.5346),
    }
    return location_map.get(location, (0, 0))

# 計算距離
def calculate_distance(coord1, coord2):
    try:
        if coord1 == (0, 0) or coord2 == (0, 0):
            logging.warning(f"無效的座標: coord1={coord1}, coord2={coord2}")
            return float('inf')
        return geodesic(coord1, coord2).km
    except Exception as e:
        logging.error(f"計算距離時發生錯誤: {e}")
        return float('inf')

# 訓練邏輯回歸模型
def train_logistic_regression():
    X = np.array([
        [5.0, 10, 1],
        [2.0, 5, 0],
        [1.0, 2, 1],
        [10.0, 30, 0],
    ])
    y = np.array([1, 0, 1, 0])
    model = LogisticRegression()
    model.fit(X, y)
    return model

logistic_model = train_logistic_regression()

# 處理 LINE 訊息的核心邏輯
def process_message(user_id, user_input):
    if not user_input.strip():
        return "請輸入訊息"

    if user_input == "查詢我的預約":
        conn = sqlite3.connect("rides.db")
        c = conn.cursor()
        c.execute("SELECT * FROM ride_records WHERE user_id = ?", (user_id,))
        user_rides = c.fetchall()
        conn.close()

        if not user_rides:
            return "你目前沒有預約紀錄。"

        latest = user_rides[-1]
        origin, destination, ride_type, time, payment = latest[2:7]

        match_found = False
        conn = sqlite3.connect("rides.db")
        c = conn.cursor()
        c.execute("SELECT * FROM ride_records WHERE user_id != ? AND ride_type = '共乘'", (user_id,))
        potential_matches = c.fetchall()
        conn.close()

        user_time = sum(int(x) * 60 ** i for i, x in enumerate(reversed(time.split(":"))))
        user_origin_coords = get_coordinates(origin)

        for match in potential_matches:
            match_origin, match_time, match_payment = match[2], match[5], match[6]
            match_origin_coords = get_coordinates(match_origin)
            match_time_value = sum(int(x) * 60 ** i for i, x in enumerate(reversed(match_time.split(":"))))

            distance = calculate_distance(user_origin_coords, match_origin_coords)
            time_diff = abs(user_time - match_time_value) // 60
            payment_same = 1 if payment == match_payment else 0

            features = np.array([[distance, time_diff, payment_same]])
            prediction = logistic_model.predict(features)[0]
            if prediction == 1:
                match_found = True
                break

        reply = f"""📋 你最近的預約如下：
🛫 出發地：{origin}
🛬 目的地：{destination}
🚘 共乘狀態：{ride_type}
🕐 預約時間：{time}
💳 付款方式：{payment}
👥 共乘配對狀態：{"✅ 已找到共乘對象！" if match_found else "⏳ 尚未有共乘對象"}
"""
        return reply

    if "到" in user_input and "我預約" not in user_input and "我使用" not in user_input:
        try:
            origin, destination = map(str.strip, user_input.split("到"))
        except ValueError:
            return "請輸入格式為『出發地 到 目的地』"

        origin_coords = get_coordinates(origin)
        dest_coords = get_coordinates(destination)
        user_states[user_id] = {
            "origin": origin,
            "destination": destination,
            "origin_lat": origin_coords[0],
            "origin_lon": origin_coords[1],
            "dest_lat": dest_coords[0],
            "dest_lon": dest_coords[1]
        }

        return (f"🚕 你要從 {origin} 到 {destination}\n請選擇是否共乘：",
                QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="我要共乘", text="我選擇共乘")),
                    QuickReplyButton(action=MessageAction(label="我要自己搭", text="我不共乘")),
                ]))

    if user_input in ["我選擇共乘", "我不共乘"]:
        ride_type = "共乘" if "共乘" in user_input else "不共乘"
        if user_id not in user_states:
            return "請先輸入『出發地 到 目的地』"

        user_states[user_id]["ride_type"] = ride_type
        return "請輸入你想預約的時間，例如：我預約 15:30"

    if user_input.startswith("我預約"):
        time = user_input.replace("我預約", "").strip()
        if user_id not in user_states or "ride_type" not in user_states[user_id]:
            return "請先輸入『出發地 到 目的地』並選擇共乘狀態"

        user_states[user_id]["time"] = time
        return (f"🕐 你選擇的時間是 {time}\n請選擇付款方式：",
                QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="LINE Pay", text="我使用 LINE Pay")),
                    QuickReplyButton(action=MessageAction(label="現金", text="我使用 現金")),
                    QuickReplyButton(action=MessageAction(label="悠遊卡", text="我使用 悠遊卡")),
                ]))

    if user_input.startswith("我使用"):
        payment = user_input.replace("我使用", "").strip()
        if user_id not in user_states or "time" not in user_states[user_id]:
            return "請先完成前面的預約步驟"

        user_states[user_id]["payment"] = payment
        data = user_states[user_id]

        conn = sqlite3.connect("rides.db")
        c = conn.cursor()
        c.execute("""
            INSERT INTO ride_records (user_id, origin, destination, ride_type, time, payment, origin_lat, origin_lon, dest_lat, dest_lon)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            data["origin"],
            data["destination"],
            data["ride_type"],
            data["time"],
            payment,
            data["origin_lat"],
            data["origin_lon"],
            data["dest_lat"],
            data["dest_lon"]
        ))
        conn.commit()

        match_found = False
        c.execute("SELECT * FROM ride_records WHERE user_id != ? AND ride_type = '共乘'", (user_id,))
        potential_matches = c.fetchall()
        conn.close()

        user_time = sum(int(x) * 60 ** i for i, x in enumerate(reversed(data["time"].split(":"))))
        user_origin_coords = (data["origin_lat"], data["origin_lon"])

        for match in potential_matches:
            match_origin_coords = (match[7], match[8])
            match_time, match_payment = match[5], match[6]
            match_time_value = sum(int(x) * 60 ** i for i, x in enumerate(reversed(match_time.split(":"))))

            distance = calculate_distance(user_origin_coords, match_origin_coords)
            time_diff = abs(user_time - match_time_value) // 60
            payment_same = 1 if payment == match_payment else 0

            features = np.array([[distance, time_diff, payment_same]])
            prediction = logistic_model.predict(features)[0]
            if prediction == 1:
                match_found = True
                break

        route_url = f"https://www.google.com/maps/dir/{data['origin']}/{data['destination']}"

        reply = f"""🎉 預約完成！
🛫 出發地：{data['origin']}
🛬 目的地：{data['destination']}
🚘 共乘狀態：{data['ride_type']}
🕐 預約時間：{data['time']}
💳 付款方式：{payment}"""

        if match_found:
            reply += "\n🚨 發現共乘對象！你和另一位使用者搭乘相同班次！"
        reply += f"\n\n📍 路線預覽：\n{route_url}"
        reply += "\n\n👉 想再預約，請再輸入『出發地 到 目的地』"

        user_states.pop(user_id, None)
        return reply

    return "請輸入格式為『出發地 到 目的地』的訊息"

# LINE Webhook 處理
def handle_message(event, reply_token):
    if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
        user_id = event.source.user_id
        user_input = event.message.text.strip()

        reply = process_message(user_id, user_input)
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            if isinstance(reply, tuple):
                text, quick_reply = reply
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text=text, quick_reply=quick_reply)]
                    )
                )
            else:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text=reply)]
                    )
                )

def webhook_handler(body, signature):
    try:
        events = handler.handle(body, signature)
        for event in events:
            if isinstance(event, MessageEvent):
                handle_message(event, event.reply_token)
        return "OK"
    except InvalidSignatureError:
        logging.error("無效的 LINE 簽名")
        return "Invalid signature"
    except Exception as e:
        logging.error(f"Webhook 處理錯誤: {e}")
        return f"Error: {str(e)}"

# Flask 應用
app = Flask(__name__)

@app.route("/webhook", methods=['POST'])
def webhook():
    body = request.get_data(as_text=True)
    signature = request.headers.get('X-Line-Signature', '')
    return webhook_handler(body, signature)

# Gradio 測試介面
def test_bot(user_id, message):
    if not user_id.strip():
        return "請輸入使用者 ID"
    if not message.strip():
        return "請輸入訊息"
    reply = process_message(user_id, message)
    if isinstance(reply, tuple):
        text, _ = reply
        return text
    return reply

# 建立 Gradio 介面
with gr.Blocks(title="共乘車 LINE Bot", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🚗 共乘車 LINE Bot")
    gr.Markdown("這是一個共乘車預約與匹配的 LINE Bot，支援 SQLite 資料庫儲存與邏輯回歸模型匹配。")
    
    with gr.Tab("Bot 測試"):
        with gr.Row():
            with gr.Column(scale=2):
                user_id_input = gr.Textbox(
                    label="使用者 ID",
                    placeholder="輸入一個模擬的使用者 ID（例如 user123）",
                    lines=1
                )
                message_input = gr.Textbox(
                    label="輸入訊息",
                    placeholder="例如：台北車站 到 台大",
                    lines=3
                )
                submit_btn = gr.Button("🚀 發送", variant="primary")
            
            with gr.Column(scale=3):
                output_text = gr.Textbox(
                    label="Bot 回應",
                    lines=8,
                    interactive=False
                )
        
        submit_btn.click(test_bot, inputs=[user_id_input, message_input], outputs=output_text)
        
        gr.Markdown("### 💡 試試這些範例:")
        with gr.Row():
            example1 = gr.Button("預約範例")
            example2 = gr.Button("查詢預約")
        
        example1.click(lambda: "台北車站 到 台大", outputs=message_input)
        example2.click(lambda: "查詢我的預約", outputs=message_input)
    
    with gr.Tab("Webhook 資訊"):
        gr.Markdown("### 📡 LINE Bot Webhook 設定")
        gr.Markdown("""
        **Webhook URL**: `http://你的主機:5000/webhook`
        
        請在 LINE Developers Console 中設定此 URL 作為您的 Webhook 端點。
        
        **環境變數需求**:
        - `LINE_CHANNEL_ACCESS_TOKEN`: LINE Bot 的 Channel Access Token
        - `LINE_CHANNEL_SECRET`: LINE Bot 的 Channel Secret
        """)
        
        status_text = gr.Textbox(
            label="系統狀態",
            value="✅ 系統運行中" if os.getenv("LINE_CHANNEL_ACCESS_TOKEN") else "⚠️ 請設定環境變數",
            interactive=False
        )

if __name__ == "__main__":
    import threading
    flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000))
    flask_thread.start()
    demo.launch(server_name="0.0.0.0", server_port=7860)