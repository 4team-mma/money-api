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
import time # ⏱️ 監控速度用
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()
logger = logging.getLogger(__name__)

# 1. 獲取設定 (兩邊通用)
@router.get("/config", response_model=Optional[AIConfigResponse], summary="⚙️ 獲取 AI 配置")
def get_ai_robot_config(db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    return db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id, AIConfig.is_active == True).first()

# 2. 儲存設定 (自動修正 URL 斜線)
@router.post("/save", summary="💾 儲存 AI 配置")
def save_ai_config(payload: AIConfigSave, db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
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
            base_url=payload.base_url.rstrip('/'), # ⚡ 防止 Windows/Mac 路徑多一個斜線
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

# 3. AI 對話接口 (整合速度監控與路徑自適應)
@router.post("/chat", summary="💬 與理財喵喵對話")
async def chat_with_meow(req: ChatRequest, db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    start_time = time.time() # ⏱️ 開始計算 AI 思考時間
    
    config = db.query(AIConfig).filter(
        AIConfig.user_id == current_user.user_id, 
        AIConfig.is_active == True
    ).first()

    # 預設配置 (若資料庫沒設定)
    if not config:
        config = AIConfig(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
            model_version="gemma3:1b",
            system_prompt=f"你現在是理財助手喵喵。當前使用者是 {current_user.name}。結尾必帶喵。"
        )

    # 抓取財務 RAG 上下文
    try:
        financial_data = AnythingService.get_structured_financial_context(db, current_user.user_id)
    except Exception as e:
        logger.error(f"財務數據讀取失敗: {str(e)}")
        financial_data = "暫時查無明細喵。"

    now_str = datetime.datetime.now().strftime("%Y-%m-%d")
    smart_prompt = f"{config.system_prompt}\n【事實數據】：今日日期 {now_str}。\n真實明細：{financial_data}\n\n【用戶問題】：{req.message}\n【指令】：請精簡回答喵！"

    async with httpx.AsyncClient() as client:
        try:
            # --- Ollama 模式 ---
            if config.provider == "ollama":
                target_url = f"{config.base_url.rstrip('/')}/api/chat"
                res = await client.post(target_url, json={
                    "model": config.model_version,
                    "messages": [{"role": "user", "content": smart_prompt}],
                    "stream": False
                }, timeout=120.0)
                reply = res.json()["message"]["content"]

            # --- AnythingLLM 模式 (自動相容 Windows/Mac 驗證路徑) ---
            elif config.provider == "anythingllm":
                # 🔐 認證繼承：解密資料庫 Key，若無則抓環境變數
                any_key = decrypt_api_key(config.api_key) if config.api_key != "none" else os.getenv("ANYTHINGLLM_KEY")
                any_ws = os.getenv("ANYTHINGLLM_WORKSPACE", "finance-al-agent")
                
                # 🌐 路徑修補：偵測是否需要補上 /api/v1 (Mac 必須要有才能過 auth)
                base_url = config.base_url.rstrip('/')
                if "/api/v1" not in base_url:
                    api_url = f"{base_url}/api/v1/workspace/{any_ws}/chat"
                else:
                    api_url = f"{base_url}/workspace/{any_ws}/chat"
                
                res = await client.post(api_url, 
                    json={"message": smart_prompt, "mode": "chat"}, 
                    headers={"Authorization": f"Bearer {any_key}"}, 
                    timeout=120.0 # 🚀 給 Mac 充足的思考時間
                )
                reply = res.json().get("textResponse", "喵... AI 沒反應。")

            # ⏱️ 效能監控日誌
            duration = round(time.time() - start_time, 2)
            logger.info(f"✨ AI 回應成功！耗時: {duration}s | 大腦: {config.provider}")
            print(f"DEBUG: [效能監控] AI 耗時: {duration} 秒")

            return {"reply": reply, "duration": duration}

        except Exception as e:
            logger.error(f"AI 連線異常: {str(e)}")
            return {"reply": f"喵... 連線失敗喵。原因：{str(e)}"}

    return {"reply": "喵喵目前不知道該用哪個大腦。"}