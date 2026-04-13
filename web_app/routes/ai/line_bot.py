import os
from fastapi import APIRouter, Request, HTTPException
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, AudioMessage, PostbackEvent,
    TemplateSendMessage, ButtonsTemplate, MessageAction
)
from web_app.database import SessionLocal
from web_app.models import Member
from web_app.utils.password import verify_password
from web_app.services.line_service import LineService

router = APIRouter()
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN', ''))
parser = WebhookParser(os.getenv('LINE_CHANNEL_SECRET', ''))

@router.post("/webhook")
async def line_webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_str = body.decode("utf-8")

    try:
        # 🌟 恢復你原本完美的防呆解析邏輯，徹底消滅 Pylance 黃線！
        parsed_data = parser.parse(body_str, signature)
        events = parsed_data if isinstance(parsed_data, list) else getattr(parsed_data, 'events', [])

        for event in events:
            if isinstance(event, MessageEvent):
                if isinstance(event.message, TextMessage):
                    await handle_async_message(event)
                elif isinstance(event.message, AudioMessage):
                    await handle_audio_message(event)
            elif isinstance(event, PostbackEvent):
                await handle_async_postback(event)
                
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        print(f"❌ Webhook Error: {e}")

    return "OK"

# ==========================================
# 1. 處理文字對話 (登入、選單、AI路由)
# ==========================================
async def handle_async_message(event):
    line_user_id = event.source.user_id
    user_msg = event.message.text.strip()
    db = SessionLocal()
    reply_content = None

    try:
        user = db.query(Member).filter(Member.line_user_id == line_user_id).first()

        if not user:
            # --- 登入與綁定邏輯 (完全保留) ---
            if user_msg.lower().startswith(("登入", "login")):
                parts = user_msg.split()
                if len(parts) == 3:
                    target_user = db.query(Member).filter((Member.email == parts[1]) | (Member.username == parts[1])).first()
                    if target_user and verify_password(parts[2], target_user.password):
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
            # --- 已登入：選單與命令路由 (完全保留) ---
            if user_msg in ["取消", "取消記帳", "取消轉帳"]:
                reply_content = TextSendMessage(text="好的，動作已經取消囉喵！")
            elif user_msg in ["選單", "menu", "幫助", "喵喵"]:
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
                # 🌟 將動腦的 AI 任務與卡片組裝交給 LineService
                reply_content = await LineService.get_ai_reply_message(user_msg, db, user)

    except Exception as e:
        print(f"❌ Logic Error: {e}")
        reply_content = TextSendMessage(text="喵嗚... 系統有點不對勁。")
    finally:
        db.close()

    if reply_content:
        line_bot_api.reply_message(event.reply_token, reply_content)

# ==========================================
# 2. 處理語音訊息
# ==========================================
async def handle_audio_message(event):
    line_user_id = event.source.user_id
    message_id = event.message.id
    db = SessionLocal()
    
    try:
        user = db.query(Member).filter(Member.line_user_id == line_user_id).first()
        if not user:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="喵！請先輸入「登入 帳號 密碼」綁定系統喵！"))
            return

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🎙️ 喵喵正在仔細聽小主人的語音..."))
        
        # 🌟 呼叫 Service 下載音檔並翻譯
        text, error = await LineService.process_audio_to_text(line_bot_api, message_id)
        
        if error or not text:
            line_bot_api.push_message(line_user_id, TextSendMessage(text=f"喵嗚... 聽不太清楚：{error or '無文字'}"))
            return
            
        # 🌟 拿到文字後，交給 Service 處理 AI 邏輯
        reply_content = await LineService.get_ai_reply_message(text, db, user)
        
        line_bot_api.push_message(line_user_id, TextSendMessage(text=f"🗣️ 你說：「{text}」"))
        line_bot_api.push_message(line_user_id, reply_content)
        
    except Exception as e:
        print(f"❌ Audio Processing Error: {e}")
        line_bot_api.push_message(line_user_id, TextSendMessage(text="喵嗚... 系統發生例外錯誤。"))
    finally:
        db.close()

# ==========================================
# 3. 處理按鈕回傳 (正式寫入資料庫)
# ==========================================
async def handle_async_postback(event):
    line_user_id = event.source.user_id
    pb_data_str = event.postback.data
    db = SessionLocal()
    
    try:
        user = db.query(Member).filter(Member.line_user_id == line_user_id).first()
        if not user: return
        
        # 🌟 將髒活 (解析 JSON、寫入 Transaction/AddRecord) 交給 LineService
        reply_content = LineService.process_postback_action(db, user, pb_data_str)
        line_bot_api.reply_message(event.reply_token, reply_content)
        
    except Exception as e:
        print(f"❌ Postback DB Error: {e}")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="喵嗚... 寫入資料庫失敗了，請稍後再試。"))
    finally:
        db.close()