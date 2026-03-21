import os
import asyncio
from fastapi import APIRouter, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# 引入你的資料庫與模型
from web_app.database import SessionLocal
from web_app.models import Member
from web_app.utils.password import verify_password
from web_app.schemas.ai import ChatRequest, LineWebhookPayload

# 引入你的 AI 核心邏輯
from web_app.routes.ai_models import chat_with_meow

router = APIRouter()

# 從環境變數讀取 LINE 的兩把鑰匙
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN', ''))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET', ''))

@router.post("/webhook")
async def line_webhook(payload: LineWebhookPayload, request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_str = body.decode("utf-8")

    try:
        handler.handle(body_str, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    line_user_id = event.source.user_id
    user_msg = event.message.text.strip()
    
    db = SessionLocal()
    reply_text = ""

    try:
        # 1. 檢查這個 LINE ID 是否已經綁定過會員
        user = db.query(Member).filter(Member.line_user_id == line_user_id).first()

        if not user:
            # --- 未登入狀態 ---
            # 支援格式： "登入 帳號 密碼" 或 "login 帳號 密碼"
            if user_msg.lower().startswith(("登入", "login")):
                parts = user_msg.split()
                if len(parts) == 3:
                    account, password = parts[1], parts[2]
                    # 嘗試用 email 或 username 搜尋 (根據你的表設計)
                    target_user = db.query(Member).filter(
                        (Member.email == account) | (Member.username == account)
                    ).first()

                    if target_user and verify_password(password, target_user.password):
                        # 驗證成功，寫入 line_user_id 進行綁定
                        target_user.line_user_id = line_user_id
                        db.commit()
                        reply_text = f"🎉 綁定成功！喵喵認得你了，{target_user.name} 喵！\n現在你可以直接跟我說話，或是開始記帳囉。"
                    else:
                        reply_text = "❌ 登入失敗：帳號或密碼錯誤，請再試一次喵！"
                else:
                    reply_text = "💡 格式錯誤喔！請輸入：\n「登入 你的帳號 你的密碼」"
            else:
                reply_text = "喵？我不認識你耶。請先輸入：\n「登入 帳號 密碼」\n來跟你的財務系統連線喵！"
        
        else:
            # --- 已登入狀態：直接對話 ---
            # 處理登出指令
            if user_msg in ["登出", "logout", "解除綁定"]:
                user.line_user_id = None
                db.commit()
                reply_text = "已幫你解除綁定囉！下次見喵～"
            else:
                # 封裝成 ChatRequest 丟給你的 ai_models.py
                req = ChatRequest(message=user_msg, persona="理財小助手喵喵")
                
                # 因為 chat_with_meow 是 async，在同步 handler 裡用 asyncio.run
                # 注意：如果 chat_with_meow 內部有複雜的 Task 可能需要封裝成非同步
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                ai_response = loop.run_until_complete(chat_with_meow(req=req, db=db, current_user=user))
                loop.close()

                reply_text = ai_response.get("reply", "喵... 我暫時無法回應。")

    except Exception as e:
        print(f"❌ LineBot Error: {str(e)}")
        reply_text = "喵嗚... 系統出了一點問題，請稍後再試。"
    finally:
        db.close()

    # 送出回覆
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )