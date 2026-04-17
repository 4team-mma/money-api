from fastapi import APIRouter, Depends, Header, Body
from sqlalchemy.orm import Session
from typing import Optional
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
    data: dict = Body(...),
    db: Session = Depends(get_db),
    text: Optional[str] = Header(None)
):
    raw_msg = data.get("message ", data.get("message", ""))
    msg = str(raw_msg).strip()
    
    uid = 6 
    auth_source = text
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
    action_status = "chat" # 新增狀態追蹤

    # 3. 處理結束語
    if any(k in msg for k in ["結束", "再見", "不用了", "拜拜", "沒事了"]):
        if uid in pending_cache: del pending_cache[uid]
        reply_text = "好的，下次見喵！"
        action_status = "exit"

    # 4. 處理二次確認 (記帳寫入)
    elif msg in ["確認", "對", "沒錯", "確定", "可以", "好", "要"]:
        pending_data = pending_cache.get(uid)
        
        # 🌟 核心修復：如果 pending_data 是列表，取第一個元素
        if isinstance(pending_data, list) and len(pending_data) > 0:
            pending_data = pending_data[0]

        if pending_data and isinstance(pending_data, dict):
            success = False
            try:
                if pending_data.get("record_type") == "transfer":
                    success = RecordsService.create_transfer(db, uid, pending_data)
                else:
                    success = RecordsService.create_add_record(db, uid, pending_data)
                
                if success:
                    del pending_cache[uid]
                    reply_text = "記好了！小主人真棒，喵喵已經更新帳本囉喵！"
                    action_status = "success"
                else:
                    reply_text = "喵... 記帳失敗了，請檢查金額或類別喵。"
                    action_status = "fail"
            except Exception as e:
                print(f"❌ 寫入資料庫出錯: {e}")
                reply_text = "喵... 資料庫不理我，沒辦法寫入喵。"
                action_status = "error"
        else:
            reply_text = "喵？小主人妳剛才沒說要記什麼呀。"
            action_status = "no_data"

    # 5. 正常解析意圖
    else:
        from web_app.schemas.ai import ChatRequest
        wrapped_req = ChatRequest(message=msg)
        result = await chat_with_meow(wrapped_req, db, current_user)
        duration = result.get("duration", 0)

        if result.get("is_command") and result.get("action_data"):
            # 存入快取，供下次「確認」使用
            pending_cache[uid] = result["action_data"]
            reply_text = f"{result['reply']} 小主人要確認嗎？喵？"
            action_status = "pending"
        else:
            reply_text = result.get("reply", "喵喵在聽...")
            action_status = "chat"

    # 🌟 WebSocket 廣播 (通知網頁端顯示對應 UI)
    try:
        await manager.send_personal_message({
            "type": "siri_sync",
            "user_query": msg,
            "ai_reply": reply_text,
            "status": action_status,
            "duration": duration,
            # 如果是 pending 狀態，把資料也傳給前端顯示卡片
            "pending_data": pending_cache.get(uid) if action_status == "pending" else None
        }, user_id=uid)
    except Exception as e:
        print(f"⚠️ [WebSocket] 廣播失敗: {e}")

    return {"reply": reply_text, "status": "success"}