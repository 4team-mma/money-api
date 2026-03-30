# web_app/routes/ai_models.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import AIConfig, Member
from ..schemas.ai import AIConfigSave, AIConfigResponse, ChatRequest
from ..dependencies import get_current_user
from ..utils.ai_security import decrypt_api_key, encrypt_api_key

# 引入服務層 (Services)
from ..services.gemini_service import GeminiService 
from ..services.ollama_service import OllamaService     
from ..services.finance_agent_service import FinanceAgentService 

from typing import Optional
import os
import time
import httpx
from dotenv import load_dotenv
import logging

load_dotenv()
router = APIRouter()
logger = logging.getLogger(__name__)

# ==========================================
# 讀取 .env 作為系統全局預設值 (System Defaults)
# ==========================================
SYS_DEFAULT_PROVIDER = os.getenv("CURRENT_AI_MODEL", "gemini") 
SYS_OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
SYS_OLLAMA_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "gemma3:1b")
SYS_GEMINI_MODEL = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-3-flash-preview")

def get_sys_default_model(provider: str) -> str:
    """根據 Provider 決定預設模型名稱"""
    return SYS_OLLAMA_MODEL if provider == "ollama" else SYS_GEMINI_MODEL

# --- 1. 獲取配置 ---
@router.get(
    "/config", 
    response_model=Optional[AIConfigResponse],
    summary="取得 AI 模型配置"
)
def get_ai_robot_config(
    provider: Optional[str] = Query(None, description="指定查詢的模型供應商"), 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    query = db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id)
    
    target_config = None
    if provider:
        target_config = query.filter(AIConfig.provider == provider).order_by(AIConfig.created_at.desc()).first()
    else:
        target_config = query.filter(AIConfig.is_active == True).first()
        if not target_config:
            target_config = query.first()

    if target_config:
        data_dict = {
            "provider": str(target_config.provider),
            "base_url": target_config.base_url,
            "model_version": target_config.model_version, 
            "system_prompt": target_config.system_prompt,
            "is_active": bool(target_config.is_active),
            "has_key": target_config.api_key is not None and target_config.api_key != "none"
        }
        return AIConfigResponse(**data_dict)
    
    return AIConfigResponse(
        provider=SYS_DEFAULT_PROVIDER,
        base_url=SYS_OLLAMA_URL if SYS_DEFAULT_PROVIDER == "ollama" else "",
        model_version=get_sys_default_model(SYS_DEFAULT_PROVIDER),
        system_prompt="你是理財小助手喵喵...",
        is_active=False,
        has_key=False
    )

# --- 2. 儲存配置 ---
@router.post(
    "/save", 
    summary="儲存或更新 AI 配置"
)
def save_ai_config(
    payload: AIConfigSave, 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    try:
        db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id).update({"is_active": False})
        
        new_key = payload.api_key
        secured_key = "none"

        if new_key and new_key != "none" and new_key.strip():
            secured_key = encrypt_api_key(new_key)
        else:
            old = db.query(AIConfig).filter(
                AIConfig.user_id == current_user.user_id,
                AIConfig.provider == payload.provider
            ).order_by(AIConfig.created_at.desc()).first()
            if old and old.api_key:
                secured_key = old.api_key

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

# --- 3. AI 對話接口 (整合智能篩選器) ---
@router.post(
    "/chat",
    summary="與 AI 喵喵對話"
)
async def chat_with_meow(
    req: ChatRequest, 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    start_time = time.time()
    db.expire_all() 

    # 1. 取得設定與安全網防護
    config = db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id, AIConfig.is_active == True).first()
    if not config:
        config = db.query(AIConfig).filter(AIConfig.user_id == 1, AIConfig.is_active == True).first()
    if not config:
        config = AIConfig(
            provider=SYS_DEFAULT_PROVIDER, base_url=SYS_OLLAMA_URL,
            model_version=get_sys_default_model(SYS_DEFAULT_PROVIDER), system_prompt="你是理財小助手喵喵喵"
        )
        
    is_on_render = os.getenv("RENDER") == "true"
    if config.provider == "ollama" and is_on_render:
        print("⚠️ [安全網攔截] 雲端環境自動降級為 Gemini 喵！")
        config.provider = "gemini"
        config.model_version = "gemini-3-flash-preview" 

    # 2. 判斷意圖與獲取財務上下文
    try:
        agent_response = await FinanceAgentService.get_context(db, current_user, req.message, req.persona)
        current_intent = agent_response["intent"]
        financial_context_instruction = agent_response["system_prompt"]
        print(f"🎯 [意圖偵測]: {current_intent}")
    except Exception as e:
        logger.error(f"FinanceAgent 讀取失敗: {str(e)}", exc_info=True)
        current_intent = "CHAT"
        financial_context_instruction = "【系統訊息】暫時無法讀取財務資料，請依一般常識回答。"

    final_system_prompt = f"{config.system_prompt}\n\n{financial_context_instruction}"

    # 預設回傳變數
    is_json_command = False
    parsed_action = None
    reply = "喵喵不知道該說什麼..."
    actual_model_used = config.model_version 

    # ==========================================
    # 🌟 攔截點：完美的二選一分流！
    # ==========================================
    # 🌟 這裡修改：把 MULTI_RECORD 也加進來
    if current_intent in ["RECORD", "MULTI_RECORD"]:
        # 🚀 通道 A：精準記帳 (強制走 Groq 高階海關)
        try:
            # 取得雙軌輸出的 JSON 字典
            groq_result = FinanceAgentService.execute_record_chain(final_system_prompt, req.message)
            
            is_json_command = True
            # 取出給前端的 Action Data
            parsed_action = groq_result.get("action_data", {})
            # 取出可愛的對話回覆
            reply = groq_result.get("reply_text", "收到喵！請確認下方的記帳卡片喵！")
            
            actual_model_used = "Groq (Llama3-8b)"
            
        except Exception as e:
            logger.error(f"Groq 解析 JSON 失敗: {str(e)}", exc_info=True)
            reply = "喵喵聽不懂這筆帳，請換個方式說喵！"
            is_json_command = False
            parsed_action = None
            actual_model_used = "Groq (Error)"

    else:
        # 💡 通道 B：其他意圖 (閒聊、查帳、手冊查詢) 走使用者選擇的大腦
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

                # 🌟 1. 引入你的工具 (假設你有這些工具，沒有的話這兩行先註解掉)
                from ..services.finance_tools import get_budget_tool, search_manual_tool
                my_tools = [get_budget_tool, search_manual_tool]

                # 🌟 2. 幫 prompt 加料，偷偷把 user_id 塞進去讓工具知道要查誰
                enhanced_prompt = f"【系統機密：當前使用者的 user_id 為 {current_user.user_id}】\n問題：{req.message}"

                # 🌟 3. 呼叫 Service，多傳遞一個 tools 參數
                result = await GeminiService.chat_async(
                    api_key=final_key,
                    model_id=config.model_version,
                    prompt=enhanced_prompt,
                    system_instruction=final_system_prompt,
                    tools=my_tools  # 傳入工具名單
                )
                reply = result["text"]
                actual_model_used = result["actual_model"]

            elif config.provider == "ollama":
                reply = await OllamaService.chat_async(
                    base_url=config.base_url,
                    model_id=config.model_version,
                    prompt=req.message,
                    system_instruction=final_system_prompt
                )

            elif config.provider == "anythingllm":
                any_key = decrypt_api_key(config.api_key) if (config.api_key and config.api_key != "none") else os.getenv("ANYTHINGLLM_KEY")
                any_ws = os.getenv("ANYTHINGLLM_WORKSPACE", "finance-al-agent")
                api_url = f"{config.base_url.rstrip('/')}/api/v1/workspace/{any_ws}/chat"
                
                async with httpx.AsyncClient() as client:
                    res = await client.post(
                        api_url, 
                        json={"message": f"{final_system_prompt}\n問題：{req.message}", "mode": "chat"}, 
                        headers={"Authorization": f"Bearer {any_key}"}, 
                        timeout=120.0
                    )
                    reply = res.json().get("textResponse", "喵... AnyThingLLM 沒回應。")

        except Exception as e:
            logger.error(f"一般對話大腦連線失敗: {str(e)}", exc_info=True)
            reply = "大腦連線失敗喵..."

    # ==========================================
    # 5. 收尾工作：更新任務與回傳
    # ==========================================
    duration = round(time.time() - start_time, 2)
    print(f"✨ [AI DEBUG] 回應成功！耗時: {duration}s")
    
    from web_app.services.game_service import GameService
    try:
        GameService.update_mission_progress(
            db=db, user_id=current_user.user_id, category='AI_聊天', note=req.message, increment=1
        )
    except Exception as game_err:
        logger.error(f"遊戲任務進度更新失敗: {str(game_err)}", exc_info=True)
    
    provider_display = f"gemini ({actual_model_used})" if config.provider == "gemini" and current_intent != "RECORD" else actual_model_used
    
    return {
        "reply": reply, 
        "duration": duration, 
        "provider": provider_display,
        "is_command": is_json_command,
        "action_data": parsed_action
    }