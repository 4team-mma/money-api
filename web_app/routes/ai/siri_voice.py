from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from datetime import datetime
import pytz
from decimal import Decimal

from web_app.database import get_db
from web_app.models import Member, AddRecord, Account # 🌟 匯入 AddRecord 與 Account
from web_app.schemas.ai import ChatRequest
from web_app.routes.ai_models import chat_with_meow

router = APIRouter()

# 暫存區與通知標記
pending_cache = {} 
voice_notif_flag = {}

# 🐱 輔助函式：對應 Python 版的 Icon 邏輯
def get_class_icon_python(class_name: str) -> str:
    icon_map = {
        '飲食': '🍔', '交通': '🚗', '居家': '🏠', '娛樂': '🎮',
        '醫療': '💊', '學習': '📚', '帳單': '🧾', '其他': '📦'
    }
    return icon_map.get(class_name, '📌')

@router.post("/siri_chat")
async def siri_chat_endpoint(req: ChatRequest, request: Request, db: Session = Depends(get_db)):
    msg = req.message.strip()
    _ = request.headers.get("authorization") 
    user_id = 6 
    tw_tz = pytz.timezone('Asia/Taipei')
    now = datetime.now(tw_tz)

    user_obj = db.query(Member).filter(Member.user_id == user_id).first()
    if not user_obj: return "喵... 找不到小主人 ID 6。"
    current_user: Member = user_obj

    # --- 1. 處理結束語 (讓捷徑停下的關鍵) ---
    if any(k in msg for k in ["結束", "再見", "不用了", "拜拜"]):
        if user_id in pending_cache: del pending_cache[user_id]
        return "好的，下次見喵！"

    # --- 2. 處理二次確認 (正式記帳) ---
    if msg in ["確認", "對", "沒錯", "確定", "可以", "好"]:
        data = pending_cache.get(user_id)
        if data:
            try:
                amt = Decimal(str(data.get("add_amount", 0)))
                # 🌟 自動尋找該使用者的第一個帳戶 (避免變成未知帳戶)
                account = db.query(Account).filter(Account.user_id == user_id).first()
                if not account: return "喵... 小主人妳還沒建立帳戶，沒辦法記帳喔！"

                # 建立新紀錄
                new_rec = AddRecord(
                    user_id=user_id,
                    add_date=now.date(),
                    add_amount=amt,
                    add_type=True if data.get("record_type") == "income" else False,
                    add_class=data.get("add_class", "其他"),
                    add_class_icon=get_class_icon_python(data.get("add_class", "其他")),
                    account_id=account.account_id, # 🌟 這裡自動填入 ID
                    add_member=data.get("add_member", "自己"),
                    add_tag=data.get("add_tag", "需要"),
                    add_note=data.get("add_note", "語音記帳")
                )
                
                # 🌟 同步更新帳戶餘額 (參考妳的 records.py)
                if new_rec.add_type is False: # 支出
                    account.current_balance -= amt
                else: # 收入
                    account.current_balance += amt

                db.add(new_rec)
                db.commit()
                
                del pending_cache[user_id]
                voice_notif_flag[user_id] = True # 🚩 觸發網頁通知
                return "記好了！小主人真棒，喵喵已經更新帳本囉喵！"
            except Exception as e:
                db.rollback()
                return f"喵... 記帳失敗了：{str(e)[:20]}"
        return "喵？小主人妳剛才沒說要記什麼呀。"

    # --- 3. 呼叫 AI 解析意圖 ---
    result = await chat_with_meow(req, db, current_user)
    
    if result.get("is_command") and result.get("action_data"):
        pending_cache[user_id] = result["action_data"]
        return f"{result['reply']} 小主人要確認記帳嗎？喵？"

    return result.get("reply", "喵喵在聽...")

@router.get("/notifications")
async def get_voice_notifications(user_id: int = 6):
    if voice_notif_flag.get(user_id):
        voice_notif_flag[user_id] = False # 領完歸零
        return {"has_new": True}
    return {"has_new": False}