import os
import asyncio
from fastapi import APIRouter, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    TemplateSendMessage, ButtonsTemplate, MessageAction
)

# 引入你的資料庫與模型
from web_app.database import SessionLocal
from web_app.models import Member
from web_app.utils.password import verify_password
from web_app.schemas.ai import ChatRequest, LineWebhookPayload

# 引入你的 AI 核心邏輯
from web_app.routes.ai_models import chat_with_meow

router = APIRouter()

# LINE API 設定
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
    reply_content = None 

    try:
        # 1. 檢查綁定狀態
        user = db.query(Member).filter(Member.line_user_id == line_user_id).first()

        if not user:
            # --- 【未登入狀態】 ---
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
                        msg = f"🎉 綁定成功！喵喵認得你了，{target_user.name} 喵！\n現在你可以直接跟我說話，或是開始記帳囉。"
                        reply_content = TextSendMessage(text=msg)
                    else:
                        reply_content = TextSendMessage(text="❌ 登入失敗：帳號或密碼錯誤喵！")
                else:
                    reply_content = TextSendMessage(text="💡 格式錯誤喔！請點擊下方按鈕參考格式喵。")
            else:
                # 未登入引導按鈕
                reply_content = TemplateSendMessage(
                    alt_text='喵？請先登入系統喵！',
                    template=ButtonsTemplate(
                        title='喵喵財務管家 (未連線)',
                        text='歡迎！請先登入以開啟理財與對話功能。',
                        actions=[
                            MessageAction(label='我要登入', text='登入 帳號 密碼'),
                            MessageAction(label='忘記密碼', text='請聯繫管理員重設密碼')
                        ]
                    )
                )
        
        else:
            # --- 【已登入狀態】 ---
            # 2. 處理特定指令
            if user_msg in ["選單", "menu", "幫助", "喵喵"]:
                reply_content = TemplateSendMessage(
                    alt_text='喵喵功能選單',
                    template=ButtonsTemplate(
                        title='喵喵理財主選單',
                        text=f'你好，{user.name}！想做什麼呢喵？',
                        actions=[
                            MessageAction(label='快速記帳(午餐100元)', text='我今天吃午餐花了100元。'),
                            MessageAction(label='查詢餘額', text='查詢本月支出'),
                            MessageAction(label='解除綁定', text='登出')
                        ]
                    )
                )
            elif user_msg in ["登出", "logout", "解除綁定", "登出"]:
                user.line_user_id = None
                db.commit()
                reply_content = TextSendMessage(text="已幫你解除綁定囉！下次見喵～")
            else:
                # 3. 🌟 橋接 AI 核心邏輯 (最安全的非同步呼叫)
                req = ChatRequest(message=user_msg, persona="理財小助手喵喵")
                try:
                    # 使用 get_event_loop 獲取目前 FastAPI 正在運行的 loop
                    loop = asyncio.get_event_loop()
                    
                    # 透過 run_coroutine_threadsafe 把 async 任務丟進 loop 執行
                    future = asyncio.run_coroutine_threadsafe(
                        chat_with_meow(req=req, db=db, current_user=user), 
                        loop
                    )
                    # 等待結果，設定 25 秒超時 (LINE 的 webhook 限制大約在 30 秒內)
                    ai_res = future.result(timeout=25) 
                    reply_text = ai_res.get("reply", "喵... 我暫時沒想法。")
                except Exception as e:
                    print(f"❌ AI Error Detail: {e}")
                    reply_text = "喵嗚... 喵喵腦袋打結了，請再試一次。"
                
                reply_content = TextSendMessage(text=reply_text)

    except Exception as e:
        print(f"❌ LineBot Error: {str(e)}")
        reply_content = TextSendMessage(text="喵嗚... 系統出了一點問題，請稍後再試。")
    finally:
        db.close()

    # 4. 送出最終回覆
    if reply_content:
        line_bot_api.reply_message(event.reply_token, reply_content)