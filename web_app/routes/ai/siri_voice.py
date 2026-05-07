# siri_voice.py
from fastapi import APIRouter, Depends, Header, Body, Request
from sqlalchemy.orm import Session
from typing import Optional
from web_app.database import get_db
from web_app.models import Member
from web_app.routes.ai_models import chat_with_meow
from web_app.services.records_service import RecordsService
from web_app.utils.jwt import verify_token
from web_app.utils.ws_manager import manager

router = APIRouter()

# 全域暫存
pending_cache = {}
siri_session = {}

@router.post("/siri_chat", summary="Siri 專用語音接口")
async def siri_chat_endpoint(
    request: Request,  
    data: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),  
    text: Optional[str] = Header(None)
):
    # 🕵️‍♂️ 1. 抓取語音訊息 (最穩遍歷方式)
    msg = ""
    for k, v in data.items():
        if k.strip() == "message":
            msg = str(v).strip()
            break
    if not msg:
        msg = str(data.get("message", "")).strip()
    
    # 🕵️‍♂️ 2. Token 解析與 UID (維持妳原本的邏輯)
    token = authorization.split(" ")[1] if authorization and "Bearer " in authorization else \
            text.split(" ")[1] if text and "Bearer " in text else \
            data.get("token")
    
    uid = 6 
    if token:
        try:
            payload = verify_token(token)
            sub_val = payload.get("sub")
            if sub_val: uid = int(sub_val)
        except: pass

    # 🕵️‍♂️ 3. 獲取使用者 (維持 current_user 命名，絕對不動！)
    user_obj = db.query(Member).filter(Member.user_id == uid).first()
    if user_obj is None:
        return {"reply": "喵... 找不到帳號。", "status": "error"}

    current_user: Member = user_obj 
    user_name = current_user.name or "小主人"
    reply_text = ""
    action_status = "chat"
    duration = 0
    display_query = msg # 用於 Web 顯示
    
    # ===== 🌟 4. 邏輯分支：分流處理 =====
    
    # A. 啟動打招呼 (最高優先權)
    if msg == "START_GREETING" or msg == "":
        siri_session[uid] = True
        reply_text = f"{user_name} 你好，歡迎使用語音功能，請問你有什麼問題嗎？喵～"
        display_query = "啟動語音助手"

    # B. 結束語
    elif any(k in msg for k in ["結束", "再見", "不用了", "拜拜", "沒事了"]):
        if uid in pending_cache: del pending_cache[uid]
        siri_session.pop(uid, None)
        reply_text = "好的，下次見喵！"
        action_status = "exit"

    # C. 二次確認
    elif msg in ["確認", "對", "沒錯", "確定", "可以", "好", "要"]:
        pending_data = pending_cache.get(uid)
        if isinstance(pending_data, list) and len(pending_data) > 0:
            pending_data = pending_data[0]

        if pending_data and isinstance(pending_data, dict):
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
                    reply_text = "喵... 記帳失敗了。"
                    action_status = "fail"
            except:
                reply_text = "喵... 資料庫出錯了。"
                action_status = "error"
        else:
            reply_text = "喵？妳剛才沒說要記什麼呀。"
            action_status = "no_data"

    # D. 正常 AI 解析 (解決問幾點、閒聊不更新畫面的問題)
    else:
        from web_app.schemas.ai import ChatRequest
        wrapped_req = ChatRequest(message=msg)
        
        # 呼叫 AI 主程式
        result = await chat_with_meow(wrapped_req, db, current_user)
        reply_text = result.get("reply", "喵喵在聽...")
        duration = result.get("duration", 0)
        
        if result.get("is_command") and result.get("action_data"):
            pending_cache[uid] = result["action_data"]
            reply_text = f"{reply_text} 小主人要確認嗎？喵？"
            action_status = "pending"

    # ===== 🌟 5. 統一 WebSocket 同步廣播 (解決同步斷掉的問題) =====
    # 不管是打招呼還是問幾點，最後都強制發送 siri_sync，保證 Web 一定會跳氣泡！
    try:
        await manager.send_personal_message({
            "type": "siri_sync", 
            "user_query": display_query, 
            "ai_reply": reply_text,
            "status": action_status, 
            "duration": duration,
            "pending_data": pending_cache.get(uid) if action_status == "pending" else None
        }, user_id=uid)
    except: pass

    # ===== 🌟 6. 回傳 JSON 字典 (確保捷徑解析不會死掉) =====
    return {"reply": reply_text, "status": "success"}
