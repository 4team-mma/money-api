# web_app/routes/ai_models.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import AIConfig, Member
from ..schemas.ai import AIConfigSave, AIConfigResponse, ChatRequest
from ..dependencies import get_current_user
from ..utils.ai_security import decrypt_api_key, encrypt_api_key
from ..services.anything_service import AnythingService 
from typing import Optional
import httpx 
import os
import datetime
import logging
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()
logger = logging.getLogger(__name__)

# 1. 獲取設定
@router.get("/config", response_model=Optional[AIConfigResponse], summary="⚙️ 獲取 AI 助手配置")
def get_ai_robot_config(db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    """
    取得目前該使用者正在啟用的 AI 助手設定。
    - **安全性**: 回傳資料不包含 API Key。
    """
    return db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id, AIConfig.is_active == True).first()

# 2. 儲存設定
@router.post("/save", summary="💾 儲存/切換 AI 配置")
def save_ai_config(payload: AIConfigSave, db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    """
    儲存新的 AI 配置或切換模型供應商。
    
    - **邏輯**:
        1. 將舊有的配置標記為非啟動狀態 (`is_active=False`)。
        2. **金鑰繼承**: 若沒傳新金鑰但舊配置有，則沿用舊金鑰。
        3. **加密**: API Key 會經過加密後才存入資料庫。
    """
    try:
        old_config = db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id, AIConfig.is_active == True).first()
        db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id).update({"is_active": False})

        new_key = payload.api_key
        if new_key and new_key != "none":
            secured_key = encrypt_api_key(new_key)
        elif old_config and old_config.api_key:
            secured_key = old_config.api_key 
        else:
            secured_key = "none"

        new_config = AIConfig(
            user_id=current_user.user_id,
            provider=payload.provider,
            api_key=secured_key,
            base_url=payload.base_url,
            model_version=payload.model_version,
            system_prompt=payload.system_prompt,
            is_active=True
        )
        db.add(new_config)
        db.commit()
        return {"success": True, "message": f"已切換至 {payload.provider} 模式喵！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 3. AI 對話接口
@router.post("/chat", summary="💬 與理財喵喵對話")
async def chat_with_meow(req: ChatRequest, db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    """
    與 AI 理財助手進行對話。

    - **RAG 增強**: 
        系統會自動從資料庫抓取使用者的**真實帳務明細**並餵給 AI。
    - **事實校點**: 
        AI 被嚴格要求必須根據真實數據回答，嚴禁編造金額。
    - **支援大腦**: 
        支援本地 Ollama 或 AnythingLLM 服務。
    """
    financial_data = "查無帳務明細喵。"
    
    config = db.query(AIConfig).filter(
        AIConfig.user_id == current_user.user_id, 
        AIConfig.is_active == True
    ).first()

    if not config:
        config = AIConfig(
            provider="ollama",
            base_url="http://localhost:11434",
            model_version="gemma3:1b",
            system_prompt=f"你現在是理財助手喵喵。當前使用者是 {current_user.name}。結尾必帶喵。"
        )

    try:
        financial_data = AnythingService.get_structured_financial_context(db, current_user.user_id)
    except Exception as e:
        logger.error(f"獲取財務數據失敗: {str(e)}")

    now_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    smart_prompt = f"""
{config.system_prompt}
【系統規範】：必須使用「繁體中文」回答。你是為 {current_user.name} 服務的理財喵喵。
【事實數據】：現在日期是 {now_str}。
以下是資料庫中 {current_user.name} 的真實明細：
{financial_data}

【指令】：嚴禁編造數據！請針對使用者的提問「{req.message}」進行簡短回答。
"""

    async with httpx.AsyncClient() as client:
        try:
            if config.provider == "ollama":
                target_url = f"{config.base_url.rstrip('/')}/api/chat"
                response = await client.post(target_url,
                    json={"model": config.model_version, "messages": [{"role": "user", "content": smart_prompt}], "stream": False},
                    timeout=120.0 
                )
                return {"reply": response.json()["message"]["content"]}

            elif config.provider == "anythingllm":
                any_key = os.getenv("ANYTHINGLLM_KEY")
                any_ws = os.getenv("ANYTHINGLLM_WORKSPACE")
                api_url = f"http://127.0.0.1:3001/api/v1/workspace/{any_ws}/chat"
                
                res = await client.post(api_url, 
                    json={"message": smart_prompt, "mode": "chat"}, 
                    headers={"Authorization": f"Bearer {any_key}"}, 
                    timeout=120.0
                )
                return {"reply": res.json().get("textResponse", "喵... 沒收到回應。")}

        except Exception as e:
            return {"reply": f"喵... 連線到 {config.provider} 失敗。錯誤：{str(e)}"}

    return {"reply": "喵喵目前不知道該用哪個大腦。"}