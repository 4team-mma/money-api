import os
import asyncio
from fastapi import APIRouter, Request, HTTPException
from linebot import LineBotApi
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    TemplateSendMessage, ButtonsTemplate, MessageAction
)
# 這裡很重要，不要引入 WebhookHandler，我們要自己解析
from linebot.models import WebhookPayload 

# 引入你的資料庫與模型
from web_app.database import SessionLocal
from web_app.models import Member
from web_app.utils.password import verify_password
from web_app.schemas.ai import ChatRequest

# 引入你的 AI 核心邏輯
from web_app.routes.ai_models import chat_with_meow

router = APIRouter()
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN', ''))

@router.post("/webhook")
async def line_webhook(request: Request):
    """
    改用完全非同步的 Webhook 進入點
    """
    body = await request.body()
    body_str = body.decode("utf-8")
    
    # 這裡直接解析 LINE 傳來的 JSON
    try:
        payload = WebhookPayload.from_json(body_str)
        for event in payload.events:
            if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
                # 🌟 關鍵：直接用 await 呼叫處理函式
                await handle_async_message(event)
    except Exception as e:
        print(f"❌ Webhook Processing Error: {e}")
    
    return "OK"

async def handle_async_message(event):
    """
    這是一個純 async 函式，可以完美使用 await chat_with_meow
    """
    line_user_id = event.source.user_id
    user_msg = event.message.text.strip()
    db = SessionLocal()
    reply_content = None

    try:
        user = db.query(Member).filter(Member.line_user_id == line_user_id).first()

        if not user:
            # --- 未登入狀態 ---
            if user_msg.lower().startswith(("登入", "login")):
                parts = user_msg.split()
                if len(parts) == 3:
                    account, password = parts[1], parts[2]
                    target_user = db.query(Member).filter(
                        (Member.email == account) | (Member.username == account)
                    ).first()

                    if target_user and verify_password(password, target_user.password):
                        target_user.line_user_id = line_user_id
                        db.commit()
                        reply_content = TextSendMessage(text=f"🎉 綁定成功！喵喵認得你了，{target_user.name} 喵！")
                    else:
                        reply_content = TextSendMessage(text="❌ 登入失敗：帳密錯誤。")
                else:
                    reply_content = TextSendMessage(text="💡 格式：登入 帳號 密碼")
            else:
                reply_content = TemplateSendMessage(
                    alt_text='請先登入',
                    template=ButtonsTemplate(
                        title='喵喵理財', text='請先登入系統',
                        actions=[MessageAction(label='我要登入', text='登入 帳號 密碼')]
                    )
                )
        else:
            # --- 已登入狀態 ---
            if user_msg in ["選單", "menu", "幫助", "喵喵"]:
                reply_content = TemplateSendMessage(
                    alt_text='選單',
                    template=ButtonsTemplate(
                        title='主選單', text=f'你好 {user.name}，要做什麼喵？',
                        actions=[
                            MessageAction(label='快速記帳(午餐100元)', text='我今天花了100元買午餐'),
                            MessageAction(label='解除綁定', text='解除綁定')
                        ]
                    )
                )
            elif user_msg in ["登出", "logout", "解除綁定"]:
                user.line_user_id = None
                db.commit()
                reply_content = TextSendMessage(text="已解除綁定喵！")
            else:
                # 🌟 終於可以大方地用 await 了！
                req = ChatRequest(message=user_msg, persona="理財小助手喵喵")
                try:
                    # 這裡是 async 呼叫 async，這輩子都不會再報 Loop Running 的錯誤
                    ai_res = await chat_with_meow(req=req, db=db, current_user=user)
                    reply_text = ai_res.get("reply", "喵... 思考中。")
                except Exception as ai_e:
                    print(f"❌ AI Core Error: {ai_e}")
                    reply_text = "喵嗚... AI 引擎有點累了，請再試一次。"
                
                reply_content = TextSendMessage(text=reply_text)

    except Exception as e:
        print(f"❌ Logic Error: {e}")
        reply_content = TextSendMessage(text="喵嗚... 系統有點不對勁。")
    finally:
        db.close()

    # 送出回覆
    if reply_content:
        line_bot_api.reply_message(event.reply_token, reply_content)