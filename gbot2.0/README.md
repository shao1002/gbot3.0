# 共乘車 LINE Bot

這是一個共乘車預約與匹配的 LINE Bot，支援 SQLite 資料庫儲存與邏輯回歸模型匹配，部署在 Hugging Face Space 上。

## 🚀 功能特色
- 支援共乘預約（出發地、目的地、時間、付款方式）
- 使用邏輯回歸模型進行共乘匹配
- 儲存預約紀錄到 SQLite 資料庫
- 提供 Gradio 網頁測試介面

## 🔧 環境變數設定
在 Hugging Face Space 的 `Settings → Repository secrets` 中添加：
- `LINE_CHANNEL_ACCESS_TOKEN`: LINE Bot 的 Channel Access Token
- `LINE_CHANNEL_SECRET`: LINE Bot 的 Channel Secret

## 📝 使用說明
1. **創建 LINE Bot**：
   - 在 [LINE Developers](https://developers.line.biz/) 創建 Messaging API Channel。
   - 獲取 Channel Access Token 和 Channel Secret。
2. **部署到 Hugging Face**：
   - 創建一個新的 Hugging Face Space，選擇 Gradio SDK。
   - 上傳 `app.py`、`requirements.txt` 和 `README.md`。
   - 設定環境變數。
3. **設定 LINE Webhook**：
   - 在 LINE Developers Console 中設定 Webhook URL：`https://<您的用戶名>-<您的space名稱>.hf.space/webhook`
4. **測試 Bot**：
   - 使用 Gradio 介面測試共乘功能。
   - 透過 LINE App 與 Bot 互動。

## 🔗 相關連結
- [LINE Developers](https://developers.line.biz/)
- [Hugging Face Spaces](https://huggingface.co/spaces)
