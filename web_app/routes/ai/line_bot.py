import os
import json
import tempfile
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Request, HTTPException
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ButtonsTemplate, MessageAction,
    PostbackEvent, FlexSendMessage,AudioMessage
)
from web_app.services.groq_service import GroqService
from web_app.database import SessionLocal
from web_app.models import Member, AddRecord, Account, Transaction
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
            # 判斷是不是「訊息事件」
            if isinstance(event, MessageEvent):
                
                # 專用道 1：如果是文字訊息
                if isinstance(event.message, TextMessage):
                    await handle_async_message(event)
                    
                # 🌟 專用道 2：如果是語音訊息 (完美並存，不會破壞原本的設定)
                elif isinstance(event.message, AudioMessage):
                    await handle_audio_message(event)
                    
            # 判斷是不是「按鈕回傳事件」
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
                req = ChatRequest(message=user_msg, persona="理財小助手喵喵")
                try:
                    ai_res = await chat_with_meow(req=req, db=db, current_user=user)
                    ai_res = ai_res or {}

                    if ai_res.get("is_command") and ai_res.get("action_data"):
                        action_data = ai_res.get("action_data") or {}

                        amount = action_data.get("add_amount", 0)
                        note = action_data.get("add_note", "無備註")
                        record_type = action_data.get("record_type", "expense")

                        try:
                            amount = int(float(amount))
                        except:
                            amount = 0

                        # ==========================================
                        # 🌟 分流：轉帳卡片 vs 收支卡片
                        # ==========================================
                        if record_type == "transfer":
                            from_acc = action_data.get("from_account", "我的錢包")
                            to_acc = action_data.get("to_account", "我的錢包")

                            if from_acc == to_acc:
                                reply_content = TextSendMessage(
                                    text="喵嗚？你沒有跟喵喵說要從哪裡轉到哪裡喔！\n請完整告訴我，例如：\n「從 國泰世華 轉 200元 到 我的錢包」喵！"
                                )
                            else:
                                postback_data = json.dumps({
                                    "act": "transfer",
                                    "amt": amount,
                                    "note": note,
                                    "f_acc": from_acc,
                                    "t_acc": to_acc
                                }, ensure_ascii=False)

                                bubble_contents = [
                                    {"type": "text", "text": "🔄 轉帳確認", "weight": "bold", "color": "#0056FF", "size": "xl"},
                                    {"type": "separator", "margin": "md"},
                                    {"type": "text", "text": f"金額：{amount} 元", "margin": "md", "size": "lg", "weight": "bold"},
                                    {"type": "text", "text": f"轉出：{from_acc}", "color": "#666666"},
                                    {"type": "text", "text": f"轉入：{to_acc}", "color": "#666666"},
                                    {"type": "text", "text": f"備註：{note}", "color": "#999999", "size": "sm"}
                                ]
                                btn_text = f"確認轉帳：{amount}元"

                                bubble = {
                                    "type": "bubble",
                                    "body": {
                                        "type": "box", "layout": "vertical",
                                        "contents": bubble_contents
                                    },
                                    "footer": {
                                        "type": "box", "layout": "horizontal", "spacing": "sm",
                                        "contents": [
                                            {
                                                "type": "button", "style": "primary", "color": "#1DB446",
                                                "action": {
                                                    "type": "postback",
                                                    "label": "✅ 確認執行",
                                                    "data": postback_data,
                                                    "displayText": btn_text
                                                }
                                            },
                                            {
                                                "type": "button", "style": "secondary",
                                                "action": {"type": "message", "label": "❌ 取消", "text": "取消轉帳"}
                                            }
                                        ]
                                    }
                                }
                                reply_content = FlexSendMessage(alt_text="請確認您的交易", contents=bubble)

                        else:
                            is_income = (record_type == "income")
                            # 🌟 Pylance 黃線殺手：把 add_class 搬到這裡來了！
                            add_class = action_data.get("add_class", "其他")

                            postback_data = json.dumps({
                                "act": "add",
                                "amt": amount,
                                "note": note,
                                "cls": add_class,
                                "inc": is_income
                            }, ensure_ascii=False)

                            bubble_contents = [
                                {"type": "text", "text": "📝 記帳確認", "weight": "bold", "color": "#1DB446", "size": "xl"},
                                {"type": "separator", "margin": "md"},
                                {"type": "text", "text": f"金額：{amount} 元", "margin": "md", "size": "lg", "weight": "bold"},
                                {"type": "text", "text": f"項目：{note}", "color": "#666666"},
                                {"type": "text", "text": f"類別：{add_class}", "color": "#666666"},
                            ]
                            btn_text = f"確認記帳：{note} {amount}元"

                            bubble = {
                                "type": "bubble",
                                "body": {
                                    "type": "box", "layout": "vertical",
                                    "contents": bubble_contents
                                },
                                "footer": {
                                    "type": "box", "layout": "horizontal", "spacing": "sm",
                                    "contents": [
                                        {
                                            "type": "button", "style": "primary", "color": "#1DB446",
                                            "action": {
                                                "type": "postback",
                                                "label": "✅ 確認執行",
                                                "data": postback_data,
                                                "displayText": btn_text
                                            }
                                        },
                                        {
                                            "type": "button", "style": "secondary",
                                            "action": {"type": "message", "label": "❌ 取消", "text": "取消"}
                                        }
                                    ]
                                }
                            }
                            reply_content = FlexSendMessage(alt_text="請確認您的交易", contents=bubble)

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
# 🌟 新增：處理 LINE 語音訊息
# ==========================================
async def handle_audio_message(event):
    line_user_id = event.source.user_id
    message_id = event.message.id # 取得這個音檔的 ID
    db = SessionLocal()
    
    try:
        user = db.query(Member).filter(Member.line_user_id == line_user_id).first()
        if not user:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="喵！請先輸入「登入 帳號 密碼」綁定系統喵！"))
            return

        # 1. 取得使用者的 GROQ API KEY (從資料庫或環境變數)
        # 這裡假設你的專案有用環境變數存 GROQ_API_KEY
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="喵... 系統尚未設定 Groq API 金鑰，無法聽懂聲音喵！"))
            return

        # 2. 下載 LINE 的音檔
        message_content = line_bot_api.get_message_content(message_id)
        
        # 建立一個暫存檔案來存 .m4a
        temp_audio_path = os.path.join(tempfile.gettempdir(), f"{message_id}.m4a")
        with open(temp_audio_path, 'wb') as fd:
            for chunk in message_content.iter_content():
                fd.write(chunk)
                
        # 先回傳一個等待訊息，讓小主人知道我們有收到
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🎙️ 喵喵正在仔細聽小主人的語音..."))
        
        # 3. 呼叫 Groq Whisper 進行翻譯
        print(f"🎙️ 準備翻譯音檔: {temp_audio_path}")
        transcribed_text = await GroqService.transcribe_audio_async(api_key=groq_api_key, file_path=temp_audio_path)
        print(f"📝 語音翻譯結果: {transcribed_text}")
        
        # 4. 把翻譯出來的文字，丟給原本的 AI 喵喵大腦處理！
        req = ChatRequest(message=transcribed_text, persona="理財小助手喵喵")
        ai_res = await chat_with_meow(req=req, db=db, current_user=user)
        ai_res = ai_res or {}
        
        # [這裡把你的 handle_async_message 裡面的 "組裝 Flex Message" 邏輯整段複製貼上過來]
        # (為了不讓這篇太長，你可以直接拿上面組裝卡片的程式碼來用)
        # 最簡單的先回傳文字測試：
        final_reply = ai_res.get("reply", "喵... 思考中。")
        
        # 使用 push_message 傳送最終結果 (因為 reply_token 只能用一次，我們剛剛已經用掉說「正在聽」了)
        line_bot_api.push_message(line_user_id, TextSendMessage(text=f"🗣️ 你說：「{transcribed_text}」\n\n{final_reply}"))

    except Exception as e:
        print(f"❌ Audio Processing Error: {e}")
        line_bot_api.push_message(line_user_id, TextSendMessage(text="喵嗚... 翻譯語音失敗了，請傳文字給我。"))
    finally:
        db.close()
        # 5. 記得刪除暫存音檔，保護 Render 容量！
        if 'temp_audio_path' in locals() and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)



# ==========================================
# 2. 處理按鈕回傳 (正式寫入資料庫)
# ==========================================
async def handle_async_postback(event):
    line_user_id = event.source.user_id
    pb_data_str = event.postback.data

    db = SessionLocal()
    try:
        user = db.query(Member).filter(Member.line_user_id == line_user_id).first()
        if not user: return

        data = json.loads(pb_data_str)
        act = data.get("act")
        amt = Decimal(str(data.get("amt", 0)))
        note = data.get("note", "無備註")

        if act == "add":
            default_acc = db.query(Account).filter(Account.user_id == user.user_id).first()
            acc_id = default_acc.account_id if default_acc else 1
            is_income = data.get("inc", False)

            new_record = AddRecord(
                user_id=user.user_id,
                add_date=datetime.now().date(),
                add_amount=amt,
                add_type=is_income,
                add_class=data.get("cls", "其他"),
                add_class_icon="📝",
                account_id=acc_id,
                add_member="自己",
                add_tag="LINE記帳",
                add_note=note
            )
            db.add(new_record)

            msg_text = "🎉 紀錄已寫入系統喵！"
            if default_acc:
                if is_income:
                    default_acc.current_balance += amt
                    msg_text = f"🎉 恭喜發財！已將【{note} {amt}元】存入，錢包變厚了喵！"
                else:
                    default_acc.current_balance -= amt
                    msg_text = f"💸 紀錄成功！已從餘額扣除【{note} {amt}元】喵！"

            db.commit()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg_text))

        elif act == "transfer":
            f_acc_name = data.get("f_acc", "")
            t_acc_name = data.get("t_acc", "")

            f_acc = db.query(Account).filter(Account.user_id == user.user_id, Account.account_name.like(f"%{f_acc_name}%")).first()
            t_acc = db.query(Account).filter(Account.user_id == user.user_id, Account.account_name.like(f"%{t_acc_name}%")).first()

            default_acc = db.query(Account).filter(Account.user_id == user.user_id).first()
            if not f_acc: f_acc = default_acc
            if not t_acc: t_acc = default_acc

            if not f_acc or not t_acc:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 轉帳失敗：找不到您指定的帳戶喵！"))
                return

            new_tx = Transaction(
                user_id=user.user_id,
                transaction_date=datetime.now().date(),
                from_account_id=f_acc.account_id,
                to_account_id=t_acc.account_id,
                transaction_note=note,
                amount=amt
            )
            db.add(new_tx)

            f_acc.current_balance -= amt
            t_acc.current_balance += amt

            db.commit()

            msg_text = f"🔄 轉帳大成功喵！\n已從【{f_acc.account_name}】轉出 {amt} 元至【{t_acc.account_name}】。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg_text))

    except Exception as e:
        print(f"❌ DB Write Error: {e}")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="喵嗚... 寫入資料庫失敗了，請稍後再試。"))
    finally:
        db.close()
