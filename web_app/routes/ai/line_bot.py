import os
import json
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Request, HTTPException
from linebot import LineBotApi, WebhookParser  
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    TemplateSendMessage, ButtonsTemplate, MessageAction,
    PostbackEvent, FlexSendMessage
)

# 匯入你的資料庫與模型
from web_app.database import SessionLocal
from web_app.models import Member, AddRecord, Account
from web_app.utils.password import verify_password
from web_app.schemas.ai import ChatRequest

# 引入你的 AI 核心邏輯
from web_app.routes.ai_models import chat_with_meow

router = APIRouter()
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN', ''))
parser = WebhookParser(os.getenv('LINE_CHANNEL_SECRET', '')) 

@router.post("/webhook")
async def line_webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_str = body.decode("utf-8")
    
    try:
        parsed_data = parser.parse(body_str, signature)
        
        events = parsed_data if isinstance(parsed_data, list) else getattr(parsed_data, 'events', [])
        
        for event in events:
            if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
                await handle_async_message(event)
            elif isinstance(event, PostbackEvent):
                await handle_async_postback(event)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        print(f"❌ Webhook Error: {e}")
    
    return "OK"

# ==========================================
# 1. 處理文字對話與 AI 解析 (準備卡片)
# ==========================================
async def handle_async_message(event):
    line_user_id = event.source.user_id
    user_msg = event.message.text.strip()
    db = SessionLocal()
    reply_content = None

    try:
        user = db.query(Member).filter(Member.line_user_id == line_user_id).first()

        if not user:
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
            if user_msg in ["取消記帳"]:
                reply_content = TextSendMessage(text="好的，這筆帳已經取消囉喵！")
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
                req = ChatRequest(message=user_msg, persona="理財小助手喵喵")
                try:
                    ai_res = await chat_with_meow(req=req, db=db, current_user=user)
                    ai_res = ai_res or {} 
                    
                    if ai_res.get("is_command") and ai_res.get("action_data"):
                        action_data = ai_res.get("action_data") or {}
                        
                        amount = action_data.get("add_amount", 0)
                        note = action_data.get("add_note", "無備註")
                        add_class = action_data.get("add_class", "飲食")
                        
                        try:
                            amount = int(float(amount))
                        except:
                            amount = 0
                        
                        record_type = action_data.get("record_type", "expense") 
                        is_income = (record_type == "income")
                        
                        postback_data = json.dumps({
                            "act": "add",
                            "amt": amount,
                            "note": note,
                            "cls": add_class,
                            "inc": is_income,        
                            "rec": record_type       
                        }, ensure_ascii=False)

                        bubble = {
                            "type": "bubble",
                            "body": {
                                "type": "box", "layout": "vertical",
                                "contents": [
                                    {"type": "text", "text": "📝 記帳確認", "weight": "bold", "color": "#1DB446", "size": "xl"},
                                    {"type": "separator", "margin": "md"},
                                    {"type": "text", "text": f"金額：{amount} 元", "margin": "md", "size": "lg", "weight": "bold"},
                                    {"type": "text", "text": f"項目：{note}", "color": "#666666"},
                                    {"type": "text", "text": f"類別：{add_class}", "color": "#666666"},
                                ]
                            },
                            "footer": {
                                "type": "box", "layout": "horizontal", "spacing": "sm",
                                "contents": [
                                    {
                                        "type": "button", "style": "primary", "color": "#1DB446",
                                        "action": {
                                            "type": "postback",
                                            "label": "✅ 確認寫入",
                                            "data": postback_data,
                                            "displayText": f"確認記帳：{note} {amount}元"
                                        }
                                    },
                                    {
                                        "type": "button", "style": "secondary",
                                        "action": {"type": "message", "label": "❌ 取消", "text": "取消記帳"}
                                    }
                                ]
                            }
                        }
                        reply_content = FlexSendMessage(alt_text="記帳確認卡片", contents=bubble)
                        
                    else:
                        reply_content = TextSendMessage(text=ai_res.get("reply", "喵... 思考中。"))
                        
                except Exception as ai_e:
                    print(f"❌ AI Core Error: {ai_e}")
                    reply_content = TextSendMessage(text="喵嗚... AI 引擎有點累了，請再試一次。")

    except Exception as e:
        print(f"❌ Logic Error: {e}")
        reply_content = TextSendMessage(text="喵嗚... 系統有點不對勁。")
    finally:
        db.close()

    if reply_content:
        line_bot_api.reply_message(event.reply_token, reply_content)

# ==========================================
# 2. 處理按鈕回傳 (正式寫入資料庫)
# ==========================================
async def handle_async_postback(event):
    line_user_id = event.source.user_id
    pb_data_str = event.postback.data
    
    db = SessionLocal()
    try:
        user = db.query(Member).filter(Member.line_user_id == line_user_id).first()
        if not user:
            return

        data = json.loads(pb_data_str)
        
        # 🌟 確認寫入
        if data.get("act") == "add":
            
            # 1. 尋找預設錢包
            default_acc = db.query(Account).filter(Account.user_id == user.user_id).first()
            acc_id = default_acc.account_id if default_acc else 1

            # 2. 提取精準變數 (解決 note 找不到的問題)
            amt = Decimal(str(data.get("amt", 0)))
            note = data.get("note", "無備註")
            is_income = data.get("inc", False) 
            record_type = data.get("rec", "expense")
            
            # (解決 record_type 未使用的問題，印出供未來 debug 參考)
            print(f"👉 本次處理紀錄類型: {record_type}, 是否為收入: {is_income}")
            
            # 3. 建立紀錄實體
            new_record = AddRecord(
                user_id=user.user_id,
                add_date=datetime.now().date(),
                add_amount=amt,
                add_type=is_income,
                add_class=data.get("cls", "飲食"),
                add_class_icon="📝",
                account_id=acc_id,
                add_member="自己",
                add_tag="LINE記帳",
                add_note=note
            )
            
            # 4. 寫入收支表
            db.add(new_record)

            # 5. 🌟 根據收入與支出，計算餘額並設定正確的回覆訊息
            msg_text = "🎉 紀錄已寫入系統喵！"
            if default_acc:
                if is_income: # 如果是收入
                    default_acc.current_balance += amt
                    msg_text = f"🎉 恭喜發財！已將【{note} {amt}元】存入，錢包變厚了喵！"
                else:         # 如果是支出
                    default_acc.current_balance -= amt
                    msg_text = f"💸 紀錄成功！已從餘額扣除【{note} {amt}元】喵！"

            # 6. 提交到資料庫
            db.commit()
            
            # 🌟 解決 msg_text 未使用的問題，將動態訊息傳給小主人
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=msg_text)
            )
            
    except Exception as e:
        print(f"❌ DB Write Error: {e}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="喵嗚... 寫入資料庫失敗了，請檢查欄位格式喵。")
        )
    finally:
        db.close()