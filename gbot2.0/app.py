import os
import sqlite3
import numpy as np
from linebot.v3.messaging import MessagingApi
from linebot.v3.webhooks import WebhookParser, MessageEvent, TextMessage
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    TextSendMessage, QuickReply, QuickReplyButton, MessageAction
)
from sklearn.linear_model import LogisticRegression
from geopy.distance import geodesic
from flask import Flask, request, abort
import logging

# 設定日誌
logging.basicConfig(level=logging.INFO)

# 初始化 Flask 應用
app = Flask(__name__)

# 初始化 LINE Bot
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("LINE_CHANNEL_SECRET")
if not channel_access_token or not channel_secret:
    raise ValueError("請設定 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 環境變數")
line_bot_api = MessagingApi(channel_access_token)
handler = WebhookParser(channel_secret)

# 使用者狀態暫存
user_states = {}

# 初始化 SQLite 資料庫
def init_db():
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

# 訓練邏輯回歸模型
def train_logistic_regression():
    X = np.array([[5.0, 10, 1], [2.0, 5, 0], [1.0, 2, 1], [10.0, 30, 0]])
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

            distance = 0
            try:
                if user_origin_coords == (0, 0) or match_origin_coords == (0, 0):
                    logging.warning(f"無效的座標: user_origin_coords={user_origin_coords}, match_origin_coords={match_origin_coords}")
                    distance = float('inf')
                else:
                    distance = geodesic(user_origin_coords, match_origin_coords).km
            except Exception as e:
                logging.error(f"計算距離時發生錯誤: {e}")
                distance = float('inf')

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
            return "請輸入格式為『出發地 到 目的地』，例如：台北車站 到 台大"

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

        return TextSendMessage(
            text=f"🚕 你要從 {origin} 到 {destination}\n請選擇是否共乘：",
            quick_reply=QuickReply(
                items=[
                    QuickReplyButton(action=MessageAction(label="我要共乘", text="我選擇共乘")),
                    QuickReplyButton(action=MessageAction(label="我要自己搭", text="我不共乘"))
                ]
            )
        )

    if user_input in ["我選擇共乘", "我不共乘"]:
        ride_type = "共乘" if "共乘" in user_input else "不共乘"
        if user_id not in user_states:
            return "請先輸入『出發地 到 目的地』"

        user_states[user_id]["ride_type"] = ride_type
        return TextSendMessage(
            text="請輸入你想預約的時間，例如：我預約 15:30"
        )

    if user_input.startswith("我預約"):
        time = user_input.replace("我預約", "").strip()
        if user_id not in user_states or "ride_type" not in user_states[user_id]:
            return "請先輸入『出發地 到 目的地』並選擇共乘狀態"

        user_states[user_id]["time"] = time
        return TextSendMessage(
            text=f"🕐 你選擇的時間是 {time}\n請選擇付款方式：",
            quick_reply=QuickReply(
                items=[
                    QuickReplyButton(action=MessageAction(label="LINE Pay", text="我使用 LINE Pay")),
                    QuickReplyButton(action=MessageAction(label="現金", text="我使用 現金")),
                    QuickReplyButton(action=MessageAction(label="悠遊卡", text="我使用 悠遊卡"))
                ]
            )
        )

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

            distance = 0
            try:
                if user_origin_coords == (0, 0) or match_origin_coords == (0, 0):
                    logging.warning(f"無效的座標: user_origin_coords={user_origin_coords}, match_origin_coords={match_origin_coords}")
                    distance = float('inf')
                else:
                    distance = geodesic(user_origin_coords, match_origin_coords).km
            except Exception as e:
                logging.error(f"計算距離時發生錯誤: {e}")
                distance = float('inf')

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
        reply += "\n\n👉 想再預約，請輸入『出發地 到 目的地』"

        user_states.pop(user_id, None)
        return TextSendMessage(text=reply)

    return TextSendMessage(text="請輸入格式為『出發地 到 目的地』的訊息，例如：台北車站 到 台大")

# LINE Webhook 處理
@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    logging.info(f"收到 Webhook 請求: body={body}, signature={signature}")
    try:
        events = handler.parse(body, signature)
        logging.info(f"成功解析事件: {events}")
        for event in events:
            if isinstance(event, MessageEvent):
                logging.info(f"處理事件: user_id={event.source.user_id}, message={event.message.text}")
                reply = process_message(event.source.user_id, event.message.text)
                line_bot_api.reply_message(event.reply_token, reply)
        return 'OK', 200
    except InvalidSignatureError as e:
        logging.error(f"無效的 LINE 簽名: {e}")
        abort(400)
    except Exception as e:
        logging.error(f"Webhook 處理錯誤: {e}")
        abort(500)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)