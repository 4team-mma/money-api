# web_app/routes/ai_models.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import AIConfig, Member
from ..schemas.ai import AIConfigSave, AIConfigResponse, ChatRequest
from ..dependencies import get_current_user
from ..utils.ai_security import decrypt_api_key, encrypt_api_key
from ..services.anything_service import AnythingService 
from ..services.gemini_service import GeminiService 
from typing import Optional
import httpx 
import os
import datetime
import logging
import time
import traceback
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()
logger = logging.getLogger(__name__)

# --- 1. 獲取配置 (完美修正 Pylance 紅線與描述) ---
@router.get("/config", response_model=Optional[AIConfigResponse])
def get_ai_robot_config(
    provider: Optional[str] = Query(None, description="指定查詢的模型供應商"), 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    query = db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id)
    
    if provider:
        # 查特定大腦的最新一筆
        config = query.filter(AIConfig.provider == provider).order_by(AIConfig.created_at.desc()).first()
    else:
        # 預設查目前生效中的
        config = query.filter(AIConfig.is_active == True).first()

    if config:
        # 🚀 終極修正：先轉字典，再用解包方式建立，Pylance 絕對不會報錯
        data_dict = {
            "provider": str(config.provider),
            "base_url": config.base_url,
            "model_version": config.model_version,
            "system_prompt": config.system_prompt,
            "is_active": bool(config.is_active),
            "has_key": config.api_key is not None and config.api_key != "none"
        }
        return AIConfigResponse(**data_dict)
    
    return None

# --- 2. 儲存配置 (保留喵喵語氣與完整邏輯) ---
@router.post("/save")
def save_ai_config(payload: AIConfigSave, db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    try:
        # 先將該使用者所有設定設為不生效
        db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id).update({"is_active": False})
        
        # 決定金鑰：如果有傳入新 Key 就加密，否則嘗試抓取該 provider 舊有的 Key
        new_key = payload.api_key
        if new_key and new_key != "none":
            secured_key = encrypt_api_key(new_key)
        else:
            old = db.query(AIConfig).filter(
                AIConfig.user_id == current_user.user_id,
                AIConfig.provider == payload.provider
            ).order_by(AIConfig.created_at.desc()).first()
            secured_key = old.api_key if old else "none"

        new_config = AIConfig(
            user_id=current_user.user_id,
            provider=payload.provider,
            api_key=secured_key,
            base_url=payload.base_url.rstrip('/') if payload.base_url else "",
            model_version=payload.model_version,
            system_prompt=payload.system_prompt,
            is_active=True
        )
        db.add(new_config)
        db.commit()
        return {"success": True, "message": f"已成功切換至 {payload.provider} 模式喵！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# --- 3. AI 對話接口 (保留所有調試日誌與邏輯) ---
@router.post("/chat")
async def chat_with_meow(req: ChatRequest, db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    start_time = time.time()
    db.expire_all() 

    config = db.query(AIConfig).filter(
        AIConfig.user_id == current_user.user_id, 
        AIConfig.is_active == True
    ).first()

    if not config:
        config = AIConfig(provider="gemini", model_version="gemini-1.5-flash", system_prompt="你是理財小助手喵喵喵")

    target_id = config.model_version if config.model_version else "gemini-1.5-flash"
    print(f"🔥 [AI DEBUG] 呼叫模型: {target_id} | 使用者: {current_user.name}")

    try:
        financial_data = AnythingService.get_structured_financial_context(db, current_user.user_id)
    except Exception:
        financial_data = "暫時抓不到財務明細喵。"

    try:
        if config.provider == "gemini":
            env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            db_key = "none"
            if config.api_key and config.api_key != "none":
                try:
                    db_key = decrypt_api_key(config.api_key)
                except: pass
            
            final_key = db_key if (db_key and len(db_key) > 10) else env_key
            if not final_key: raise Exception("找不到有效 API Key 喵！")

            reply = await GeminiService.chat_async(
                api_key=final_key,
                model_id=target_id,
                prompt=req.message,
                system_instruction=f"{config.system_prompt}\n【事實數據】：{financial_data}"
            )

        elif config.provider == "ollama":
            async with httpx.AsyncClient() as client:
                res = await client.post(f"{config.base_url}/api/chat", json={
                    "model": config.model_version,
                    "messages": [{"role": "user", "content": f"{config.system_prompt}\n數據：{financial_data}\n問題：{req.message}"}],
                    "stream": False
                }, timeout=120.0)
                reply = res.json()["message"]["content"]

        elif config.provider == "anythingllm":
            any_key = decrypt_api_key(config.api_key) if config.api_key != "none" else os.getenv("ANYTHINGLLM_KEY")
            any_ws = os.getenv("ANYTHINGLLM_WORKSPACE", "finance-al-agent")
            api_url = f"{config.base_url.rstrip('/')}/api/v1/workspace/{any_ws}/chat"
            async with httpx.AsyncClient() as client:
                res = await client.post(api_url, 
                    json={"message": f"{config.system_prompt}\n數據：{financial_data}\n問題：{req.message}", "mode": "chat"}, 
                    headers={"Authorization": f"Bearer {any_key}"}, timeout=120.0)
                reply = res.json().get("textResponse", "喵... AnyThingLLM 沒回應。")
        else:
            reply = "喵喵目前不知道該用哪個大腦。"

        duration = round(time.time() - start_time, 2)
        print(f"✨ [AI DEBUG] 回應成功！耗時: {duration}s")
        return {"reply": reply, "duration": duration, "provider": config.provider}

    except Exception as e:
        traceback.print_exc()
        return {"reply": f"喵... 系統連線失敗: {str(e)[:50]}", "duration": 0, "provider": config.provider}