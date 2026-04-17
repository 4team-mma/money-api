from fastapi import APIRouter, Depends, Header, Body
from sqlalchemy.orm import Session
from typing import Optional, Any
from web_app.database import get_db
from web_app.models import Member
from web_app.routes.ai_models import chat_with_meow
from web_app.services.records_service import RecordsService
from web_app.utils.jwt import verify_token
from web_app.utils.ws_manager import manager

router = APIRouter()

# 全域暫存與通知字典
pending_cache = {}
voice_notif_data = {}  

@router.post("/siri_chat", summary="Siri 專用語音接口")
async def siri_chat_endpoint(
    # 🌟 使用 Body(None) 接收原始字典，繞過 Pydantic 嚴格檢查空格
    data: dict = Body(...),
    db: Session = Depends(get_db),
    # 🌟 直接讀取你捷徑裡設定的 "text" 標頭
    text: Optional[str] = Header(None)
):
    # 🕵️‍♂️ 1. 抓取語音訊息 (相容 "message" 或 "message " 帶空格)
    raw_msg = data.get("message ", data.get("message", ""))
    msg = str(raw_msg).strip()
    
    # 🕵️‍♂️ 2. 身分識別邏輯 (讀取 text 標頭)
    uid = 6  # 預設 ID
    auth_source = text  # 你捷徑裡是用 text 傳送 Bearer Token
    
    if auth_source and "Bearer " in auth_source:
        try:
            token = auth_source.split(" ")[1]
            payload = verify_token(token)
            sub_val = payload.get("sub")
            if sub_val is not None:
                uid = int(sub_val)
        except Exception as e:
            print(f"⚠️ Token 解析失敗: {e}")

    user_obj = db.query(Member).filter(Member.user_id == uid).first()
    if user_obj is None:
        return {"reply": "喵... 找不到帳號，請檢查 Token 喵。", "status": "error"}

    current_user: Member = user_obj
    reply_text = ""
    duration = 0

    # 3. 處理結束語
    if any(k in msg for k in ["結束", "再見", "不用了", "拜拜", "沒事了"]):
        if uid in pending_cache: del pending_cache[uid]
        reply_text = "好的，下次見喵！"

    # 4. 處理二次確認
    elif msg in ["確認", "對", "沒錯", "確定", "可以", "好", "要"]:
        pending_data = pending_cache.get(uid)
        if pending_data:
            success = False
            if pending_data.get("record_type") == "transfer":
                success = RecordsService.create_transfer(db, uid, pending_data)
            else:
                success = RecordsService.create_add_record(db, uid, pending_data)

            if success:
                del pending_cache[uid]
                reply_text = "記好了！小主人真棒，喵喵已經更新帳本囉喵！"
                voice_notif_data[uid] = {
                    "reply": reply_text,
                    "status": "success",
                    "type": "record_added"
                }
            else:
                reply_text = "喵... 記帳過程出了一點小問題喵。"
        else:
            reply_text = "喵？小主人妳剛才沒說要記什麼呀。"

    # 5. 正常解析意圖 (這裡把 msg 包裝回原本 ChatRequest 期待的樣子傳給 chat_with_meow)
    else:
        from web_app.schemas.ai import ChatRequest
        wrapped_req = ChatRequest(message=msg)
        result = await chat_with_meow(wrapped_req, db, current_user)
        duration = result.get("duration", 0)

        if result.get("is_command") and result.get("action_data"):
            pending_cache[uid] = result["action_data"]
            reply_text = f"{result['reply']} 小主人要確認嗎？喵？"
        else:
            reply_text = result.get("reply", "喵喵在聽...")

    # 🌟 WebSocket 廣播
    try:
        await manager.send_personal_message({
            "type": "siri_sync",
            "user_query": msg,
            "ai_reply": reply_text,
            "duration": duration
        }, user_id=uid)
    except Exception as e:
        print(f"⚠️ [WebSocket] 廣播失敗: {e}")

    return {"reply": reply_text, "status": "success"}

@router.get("/notifications")
async def get_voice_notifications(user_id: int = 6):
    data = voice_notif_data.get(user_id)
    if data:
        del voice_notif_data[user_id]
        return {"has_new": True, **data}
    return {"has_new": False}