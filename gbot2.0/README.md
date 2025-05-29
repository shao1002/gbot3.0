# LINE Bot with Google Gemini AI

這是一個結合 Google Gemini AI 的 LINE Bot 應用，支援智能對話並提供 Gradio 網頁測試介面。

## 🚀 功能特色
- 接收 LINE 訊息並使用 Gemini AI 生成智能回應
- 支援網頁測試介面（Gradio）
- 免費使用 Google AI Studio API

## 🔧 環境變數設定
在 Hugging Face Space 的 `Settings → Repository secrets` 中添加：
- `LINE_CHANNEL_ACCESS_TOKEN`: LINE Bot 的 Channel Access Token
- `LINE_CHANNEL_SECRET`: LINE Bot 的 Channel Secret
- `GEMINI_API_KEY`: Google AI Studio 的 API Key

## 📝 使用說明
1. **獲取 Google AI Studio API Key**：
   - 前往 [Google AI Studio](https://aistudio.google.com/)，登入 Google 帳號。
   - 點擊 "Get API key" 並生成 API Key。
2. **創建 LINE Bot**：
   - 在 [LINE Developers](https://developers.line.biz/) 創建 Messaging API Channel。
   - 獲取 Channel Access Token 和 Channel Secret。
3. **部署到 Hugging Face**：
   - 創建一個新的 Hugging Face Space，選擇 Gradio SDK。
   - 上傳 `app.py`、`requirements.txt` 和 `README.md`。
   - 設定環境變數。
4. **設定 LINE Webhook**：
   - 在 LINE Developers Console 中設定 Webhook URL：`https://<您的用戶名>-linebot-gemini.hf.space/webhook`
5. **測試 Bot**：
   - 使用 Gradio 介面測試 AI 回應。
   - 透過 LINE App 與 Bot 對話。

## 🔗 相關連結
- [Google AI Studio](https://aistudio.google.com/)
- [LINE Developers](https://developers.line.biz/)
- [Hugging Face Spaces](https://huggingface.co/spaces)

## 🛠️ 故障排除
- **Webhook 無回應**：檢查 Hugging Face Space 是否運行，確認 Webhook URL 正確。
- **API 錯誤**：確保 `GEMINI_API_KEY` 有效且未超過配額。
- **日誌檢查**：在 Hugging Face 的 Logs 標籤查看錯誤詳情。