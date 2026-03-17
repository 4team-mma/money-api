# web_app/routes/ai/line_bot.py
import os
from fastapi import APIRouter, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from web_app.schemas.ai import LineWebhookPayload

router = APIRouter()

# 從環境變數讀取 LINE 的兩把鑰匙
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN', ''))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET', ''))

@router.post("/webhook")
async def line_webhook(payload: LineWebhookPayload, request: Request):
    # 取得 LINE 傳過來的簽章
    signature = request.headers.get("X-Line-Signature", "")
    
    # 取得完整的 request body
    body = await request.body()
    body_str = body.decode("utf-8")

    try:
        # 把訊息交給 handler 處理
        handler.handle(body_str, signature)
    except InvalidSignatureError:
        print("⚠️ 簽章驗證失敗！請檢查 LINE_CHANNEL_SECRET 是否正確。")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        print(f"⚠️ Webhook 發生錯誤: {e}")

    return "OK"

# 當收到文字訊息時的處理邏輯
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    
    # [測試階段] 先讓喵喵當一隻鸚鵡，證明連線成功！
    reply_text = f"喵喵收到你的訊息了：{user_msg}"
    
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )