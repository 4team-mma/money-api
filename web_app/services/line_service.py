# web_app/services/line_service.py
# 它負責 「音檔處理」、「AI 卡片組裝」 與 「資料庫寫入」。
import os
import json
import tempfile
from datetime import datetime
from decimal import Decimal
from linebot.models import TextSendMessage, FlexSendMessage
from web_app.services.groq_service import GroqService
from web_app.schemas.ai import ChatRequest
from web_app.routes.ai_models import chat_with_meow
from web_app.models import AddRecord, Account, Transaction

class LineService:
    @staticmethod
    async def process_audio_to_text(line_bot_api, message_id: str):
        """處理音檔下載與語音辨識"""
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            return None, "喵... 系統尚未設定 Groq API 金鑰。"
        
        try:
            message_content = line_bot_api.get_message_content(message_id)
            temp_audio_path = os.path.join(tempfile.gettempdir(), f"{message_id}.m4a")
            
            with open(temp_audio_path, 'wb') as fd:
                for chunk in message_content.iter_content():
                    fd.write(chunk)
            
            text = await GroqService.transcribe_audio_async(api_key=groq_api_key, file_path=temp_audio_path)
            
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            
            return text, None
        except Exception as e:
            print(f"❌ Audio Service Error: {e}")
            return None, str(e)

    @staticmethod
    async def get_ai_reply_message(user_msg: str, db, current_user):
        """處理 AI 邏輯並回傳對應的 LINE 訊息物件"""
        req = ChatRequest(message=user_msg, persona="理財小助手喵喵")
        try:
            ai_res = await chat_with_meow(req=req, db=db, current_user=current_user)
            ai_res = ai_res or {}

            if ai_res.get("is_command") and ai_res.get("action_data"):
                return LineService._build_flex_message(ai_res.get("action_data", {}))
            else:
                return TextSendMessage(text=ai_res.get("reply", "喵... 思考中。"))
        except Exception as e:
            print(f"❌ AI Core Error: {e}")
            return TextSendMessage(text="喵嗚... AI 引擎有點累了，請再試一次。")

    @staticmethod
    def _build_flex_message(action_data: dict):
        """內部方法：組裝 Flex Message 卡片"""
        amount = action_data.get("add_amount", 0)
        note = action_data.get("add_note", "無備註")
        record_type = action_data.get("record_type", "expense")

        try:
            amount = int(float(amount))
        except:
            amount = 0

        if record_type == "transfer":
            from_acc = action_data.get("from_account", "我的錢包")
            to_acc = action_data.get("to_account", "我的錢包")
            if from_acc == to_acc:
                return TextSendMessage(text="喵嗚？你沒有跟喵喵說要從哪裡轉到哪裡喔！\n範例：「從 國泰世華 轉 200元 到 我的錢包」喵！")

            postback_data = json.dumps({"act": "transfer", "amt": amount, "note": note, "f_acc": from_acc, "t_acc": to_acc}, ensure_ascii=False)
            bubble_contents = [
                {"type": "text", "text": "🔄 轉帳確認", "weight": "bold", "color": "#0056FF", "size": "xl"},
                {"type": "separator", "margin": "md"},
                {"type": "text", "text": f"金額：{amount} 元", "margin": "md", "size": "lg", "weight": "bold"},
                {"type": "text", "text": f"轉出：{from_acc}", "color": "#666666"},
                {"type": "text", "text": f"轉入：{to_acc}", "color": "#666666"},
                {"type": "text", "text": f"備註：{note}", "color": "#999999", "size": "sm"}
            ]
            btn_text, color = f"確認轉帳：{amount}元", "#0056FF"
        else:
            add_class = action_data.get("add_class", "其他")
            is_income = (record_type == "income")
            postback_data = json.dumps({"act": "add", "amt": amount, "note": note, "cls": add_class, "inc": is_income}, ensure_ascii=False)
            bubble_contents = [
                {"type": "text", "text": "📝 記帳確認", "weight": "bold", "color": "#1DB446", "size": "xl"},
                {"type": "separator", "margin": "md"},
                {"type": "text", "text": f"金額：{amount} 元", "margin": "md", "size": "lg", "weight": "bold"},
                {"type": "text", "text": f"項目：{note}", "color": "#666666"},
                {"type": "text", "text": f"類別：{add_class}", "color": "#666666"},
            ]
            btn_text, color = f"確認記帳：{note} {amount}元", "#1DB446"

        bubble = {
            "type": "bubble",
            "body": {"type": "box", "layout": "vertical", "contents": bubble_contents},
            "footer": {
                "type": "box", "layout": "horizontal", "spacing": "sm",
                "contents": [
                    {"type": "button", "style": "primary", "color": color, "action": {"type": "postback", "label": "✅ 確認執行", "data": postback_data, "displayText": btn_text}},
                    {"type": "button", "style": "secondary", "action": {"type": "message", "label": "❌ 取消", "text": "取消"}}
                ]
            }
        }
        return FlexSendMessage(alt_text="請確認您的交易", contents=bubble)

    @staticmethod
    def process_postback_action(db, user, pb_data_str: str):
        """處理按鈕回傳的資料庫寫入邏輯"""
        data = json.loads(pb_data_str)
        act = data.get("act")
        amt = Decimal(str(data.get("amt", 0)))
        note = data.get("note", "無備註")

        if act == "add":
            default_acc = db.query(Account).filter(Account.user_id == user.user_id).first()
            acc_id = default_acc.account_id if default_acc else 1
            is_income = data.get("inc", False)

            new_record = AddRecord(
                user_id=user.user_id, add_date=datetime.now().date(), add_amount=amt,
                add_type=is_income, add_class=data.get("cls", "其他"), add_class_icon="📝",
                account_id=acc_id, add_member="自己", add_tag="LINE記帳", add_note=note
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
            return TextSendMessage(text=msg_text)

        elif act == "transfer":
            f_acc_name, t_acc_name = data.get("f_acc", ""), data.get("t_acc", "")
            f_acc = db.query(Account).filter(Account.user_id == user.user_id, Account.account_name.like(f"%{f_acc_name}%")).first()
            t_acc = db.query(Account).filter(Account.user_id == user.user_id, Account.account_name.like(f"%{t_acc_name}%")).first()
            
            default_acc = db.query(Account).filter(Account.user_id == user.user_id).first()
            if not f_acc: f_acc = default_acc
            if not t_acc: t_acc = default_acc

            if not f_acc or not t_acc:
                return TextSendMessage(text="❌ 轉帳失敗：找不到您指定的帳戶喵！")

            new_tx = Transaction(
                user_id=user.user_id, transaction_date=datetime.now().date(),
                from_account_id=f_acc.account_id, to_account_id=t_acc.account_id,
                transaction_note=note, amount=amt
            )
            db.add(new_tx)
            f_acc.current_balance -= amt
            t_acc.current_balance += amt
            db.commit()

            return TextSendMessage(text=f"🔄 轉帳大成功喵！\n已從【{f_acc.account_name}】轉出 {amt} 元至【{t_acc.account_name}】。")