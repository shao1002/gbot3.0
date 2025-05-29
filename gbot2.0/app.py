import gradio as gr
import os
import json
import requests
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import logging

# 設定日誌
logging.basicConfig(level=logging.INFO)

# 從環境變數獲取憑證
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

def call_gemini_api(message):
    """調用 Google Gemini API 生成回應"""
    if not GEMINI_API_KEY:
        return "錯誤：未設定 GEMINI_API_KEY 環境變數"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    
    headers = {
        'Content-Type': 'application/json',
    }
    
    data = {
        "contents": [
            {
                "parts": [
                    {"text": message}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 1024,
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()
        logging.info(f"Gemini API 回應: {result}")
        
        if 'candidates' in result and len(result['candidates']) > 0:
            reply_text = result['candidates'][0]['content']['parts'][0]['text']
            return reply_text[:5000]  # 限制回應長度以符合 LINE 限制
        else:
            return "抱歉，我無法回應您的問題。"
            
    except requests.exceptions.RequestException as e:
        logging.error(f"API 請求錯誤: {e}")
        if response.status_code == 429:
            return "錯誤：已超過 Gemini API 配額，請稍後再試。"
        return "抱歉，服務暫時無法使用。"
    except KeyError as e:
        logging.error(f"回應格式錯誤: {e}")
        return "抱歉，處理回應時發生錯誤。"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """處理 LINE 訊息"""
    user_message = event.message.text
    reply_text = call_gemini_api(user_message)
    
    # 回覆用戶
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

def webhook_handler(body, signature):
    """處理 LINE Webhook 請求"""
    try:
        handler.handle(body, signature)
        return "OK"
    except InvalidSignatureError:
        logging.error("無效的 LINE 簽名")
        return "Invalid signature"
    except Exception as e:
        logging.error(f"Webhook 處理錯誤: {e}")
        return f"Error: {str(e)}"

def test_bot(message):
    """Gradio 介面測試功能"""
    if not message.strip():
        return "請輸入測試訊息"
    return call_gemini_api(message)

# 建立 Gradio 介面
with gr.Blocks(title="LINE Bot with Gemini", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🤖 LINE Bot with Google Gemini")
    gr.Markdown("這是一個使用 Google Gemini AI 的 LINE Bot 測試介面")
    
    with gr.Tab("Bot 測試"):
        with gr.Row():
            with gr.Column(scale=2):
                input_text = gr.Textbox(
                    label="輸入測試訊息",
                    placeholder="在這裡輸入想要測試的訊息...",
                    lines=3
                )
                submit_btn = gr.Button("🚀 發送", variant="primary")
            
            with gr.Column(scale=3):
                output_text = gr.Textbox(
                    label="Gemini AI 回應",
                    lines=8,
                    interactive=False
                )
        
        submit_btn.click(test_bot, inputs=input_text, outputs=output_text)
        
        gr.Markdown("### 💡 試試這些範例:")
        with gr.Row():
            example1 = gr.Button("介紹自己