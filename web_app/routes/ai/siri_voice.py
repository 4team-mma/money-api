from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from typing import Optional
from web_app.database import get_db
from web_app.models import Member
from web_app.schemas.ai import ChatRequest
from web_app.routes.ai_models import chat_with_meow
from web_app.services.records_service import RecordsService
from web_app.utils.jwt import verify_token # 🌟 確保這裡是用妳 jwt.py 裡的驗證函式

router = APIRouter()

# 暫存區與通知標記 (全域)
pending_cache = {} 
voice_notif_flag = {}

@router.post("/siri_chat", summary="Siri 專用語音接口")
async def siri_chat_endpoint(
    req: ChatRequest, 
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None) # 🌟 改為選填標頭，避開 401
):
    msg = req.message.strip()
    
    # 🕵️‍♂️ 身分識別邏輯：優先解 Token，失敗就用 ID 6
    uid = 6 
    if authorization and "Bearer " in authorization:
        try:
            token = authorization.split(" ")[1]
            payload = verify_token(token)
            # 解決 Pylance 報錯：先抓出 sub 並確認它不是 None
            sub_val = payload.get("sub")
            if sub_val is not None:
                uid = int(sub_val)
        except Exception as e:
            print(f"⚠️ Token 解析失敗 (使用預設 ID 6): {e}")

    # 取得使用者物件 (消滅紅線)
    user_obj = db.query(Member).filter(Member.user_id == uid).first()
    if user_obj is None:
        return "喵... 找不到帳號，請檢查資料庫喵。"
    current_user: Member = user_obj

    # 1. 處理結束語 (讓捷徑聽懂何時該停)
    if any(k in msg for k in ["結束", "再見", "不用了", "拜拜", "沒事了"]):
        if uid in pending_cache: del pending_cache[uid]
        return "好的，下次見喵！"

    # 2. 處理二次確認 (記帳寫入)
    if msg in ["確認", "對", "沒錯", "確定", "可以", "好", "要"]:
        data = pending_cache.get(uid)
        if data:
            # 💡 呼叫大臣：RecordsService 會自動判斷轉帳或收支
            success = False
            if data.get("record_type") == "transfer":
                success = RecordsService.create_transfer(db, uid, data)
            else:
                success = RecordsService.create_add_record(db, uid, data)
            
            if success:
                del pending_cache[uid]
                voice_notif_flag[uid] = True # 🚩 標記前端領取通知
                return "記好了！小主人真棒，喵喵已經更新帳本囉喵！"
            return "喵... 記帳過程出了一點小問題喵。"
        return "喵？小主人妳剛才沒說要記什麼呀。"

    # 3. 正常解析意圖
    result = await chat_with_meow(req, db, current_user)
    
    if result.get("is_command") and result.get("action_data"):
        pending_cache[uid] = result["action_data"]
        return f"{result['reply']} 小主人要確認嗎？喵？"

    return result.get("reply", "喵喵在聽...")

@router.get("/notifications")
async def get_voice_notifications(user_id: int = 6):
    # 這裡暫時保留 user_id 參數供前端手動傳入
    if voice_notif_flag.get(user_id):
        voice_notif_flag[user_id] = False
        return {"has_new": True}
    return {"has_new": False}