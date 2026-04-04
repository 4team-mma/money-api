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
from ..services.groq_service import GroqService

from typing import Optional
import os
import time
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
AI_BRAIN_VERSION = os.getenv("AI_BRAIN_VERSION", "v1")


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
            "has_key": target_config.api_key is not None and target_config.api_key != "none",
            "brain_version": target_config.brain_version
        }
        return AIConfigResponse(**data_dict)

    return AIConfigResponse(
        provider=SYS_DEFAULT_PROVIDER,
        base_url=SYS_OLLAMA_URL if SYS_DEFAULT_PROVIDER == "ollama" else "",
        model_version=get_sys_default_model(SYS_DEFAULT_PROVIDER),
        system_prompt="你是理財小助手喵喵...",
        is_active=False,
        has_key=False,
        brain_version="v1" # 🌟 確保這裡有保底值
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
            is_active=True,
            # 🌟 新增這一行，才能把 v1/v2 存進資料庫
            brain_version=payload.brain_version 
        )
        db.add(new_config)
        db.commit()
        return {"success": True, "message": f"已成功切換至 {payload.provider} 模式喵！"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# --- 3. AI 對話接口 (整合智能篩選器) ---
@router.post("/chat", summary="與 AI 喵喵對話")
async def chat_with_meow(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    start_time = time.time()
    db.expire_all()

    # 1. 取得設定：使用絕對保險機制，確保 config 絕對不是 None
    db_config = db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id, AIConfig.is_active == True).first()
    
    # 如果抓不到當前使用者的，抓系統預設的 (user_id=1)
    if not db_config:
        db_config = db.query(AIConfig).filter(AIConfig.user_id == 1, AIConfig.is_active == True).first()

    # 🌟 徹底消除紅線的核心：如果連預設都沒有，手動建立一個記憶體物件
    if db_config:
        config = db_config
    else:
        config = AIConfig(
            provider=SYS_DEFAULT_PROVIDER,
            base_url=SYS_OLLAMA_URL,
            model_version=get_sys_default_model(SYS_DEFAULT_PROVIDER),
            system_prompt="你是一個親切的理財助手喵喵，說話結尾要帶喵~"
        )
    
    # 到這一步，Pylance 就知道 config 絕對有屬性了！
    
    # 2. 環境判斷
    is_on_render = os.getenv("RENDER") == "true"

    # 3. 提取指令：只拿最後一句話
    latest_query = req.message.split("小主人：")[-1].strip() if "小主人：" in req.message else req.message

    # 4. 判斷意圖
    try:
        agent_response = await FinanceAgentService.get_context(
            db, current_user, latest_query, req.persona, version=config.brain_version
        )
        current_intent = agent_response["intent"]
        financial_context_instruction = agent_response["system_prompt"]
        print(f"🎯 [意圖偵測]: {current_intent}")
    except Exception as e:
        logger.error(f"FinanceAgent Error: {str(e)}")
        current_intent = "CHAT"
        agent_response = {"intent": "CHAT", "confidence": 0.0}
        financial_context_instruction = "【系統訊息】暫時無法讀取財務資料。"

    final_system_prompt = f"{config.system_prompt}\n\n{financial_context_instruction}"

    # 初始化回傳變數
    is_json_command = False
    parsed_action = None
    reply = "喵喵不知道該說什麼..."
    actual_model_used = config.model_version

    # ==========================================
    # 5. 意圖分流處理
    # ==========================================
    if current_intent in ["RECORD", "MULTI_RECORD"]:
        # 🚀 通道 A：記帳 (強制走 Groq)
        try:
            groq_result = FinanceAgentService.execute_record_chain(final_system_prompt, latest_query)
            is_json_command = True
            parsed_action = groq_result.get("action_data", {})
            reply = groq_result.get("reply_text", "已記好囉喵！")
            actual_model_used = "Groq (Llama-Record)"
        except Exception as e:
            logger.error(f"Groq 解析 JSON 失敗: {str(e)}")
            reply = "喵喵聽不懂這筆帳，請換個方式說喵！"

    else:
        # 💡 通道 B：其他意圖
        try:
            # 🌟 邏輯：如果在 Render 且是 QUERY 意圖，自動導向 Groq 70B
            active_provider = config.provider
            active_model = config.model_version

            if current_intent == "QUERY" and is_on_render:
                active_provider = "groq"
                active_model = "llama-3.3-70b-versatile"
                print(f"🚀 [雲端優化] QUERY 自動切換至 Groq 70B")

            # A. Gemini 處理
            if active_provider == "gemini":
                env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                db_key = decrypt_api_key(config.api_key) if config.api_key and config.api_key != "none" else None
                f_key = db_key or env_key
                if not f_key: raise Exception("Missing Key")

                from ..services.finance_tools import get_budget_tool, search_manual_tool
                res = await GeminiService.chat_async(
                    api_key=str(f_key), model_id=active_model,
                    prompt=f"【機密 user_id: {current_user.user_id}】\n問題：{req.message}",
                    system_instruction=final_system_prompt,
                    tools=[get_budget_tool, search_manual_tool]
                )
                reply, actual_model_used = res["text"], res["actual_model"]

            # B. Groq 處理
            elif active_provider == "groq":
                env_key = os.getenv("GROQ_API_KEY")
                db_key = decrypt_api_key(config.api_key) if config.api_key and config.api_key != "none" else None
                f_key = db_key or env_key
                if not f_key: raise Exception("Missing Key")

                reply = await GroqService.chat_async(
                    api_key=str(f_key), model_id=active_model,
                    prompt=req.message, system_instruction=final_system_prompt
                )
                actual_model_used = active_model

            # C. Ollama 處理
            elif active_provider == "ollama":
                if is_on_render:
                    reply = "雲端環境暫不支援 Ollama，請手動切換至 Gemini 或 Groq 喵。"
                else:
                    # 這裡加上 str() 包裝 config.base_url 消除紅線
                    reply = await OllamaService.chat_async(
                        base_url=str(config.base_url or "http://localhost:11434"),
                        model_id=active_model,
                        prompt=req.message,
                        system_instruction=final_system_prompt
                    )

        except Exception as e:
            logger.error(f"AI Chat Error: {str(e)}", exc_info=True)
            reply = f"連線失敗喵... ({str(e)})"

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

    # ==========================================
    # 🌟 核心新增：自動將對話存入「意圖審核日誌」(資料飛輪)
    # ==========================================
    try:
        # 這裡需要引入你的模型類別與 Decimal
        from ..models import IntentReviewLog
        from decimal import Decimal

        # 取得意圖識別時的信心度 (預設為 1.0 若抓不到)
        conf_val = agent_response.get("confidence", 1.0)

        new_review_log = IntentReviewLog(
            user_id=current_user.user_id,
            user_message=req.message,          # 小主人的原始輸入
            predicted_intent=current_intent,   # AI 猜測的意圖 (V2模型結果)
            confidence_score=Decimal(str(conf_val)), # 轉成資料庫需要的 Decimal
            llm_response=reply,                # 🌟 儲存 AI 實際回覆的文字內容
            is_reviewed=0                      # 標記為「待處理」
        )
        db.add(new_review_log)
        db.commit() # 這裡 commit 確保 log 存入
    except Exception as log_err:
        logger.error(f"❌ 寫入對話審核日誌失敗: {str(log_err)}")
        db.rollback()
    # ==========================================

    provider_display = f"gemini ({actual_model_used})" if config.provider == "gemini" and current_intent != "RECORD" else actual_model_used

    return {
        "reply": reply,
        "duration": duration,
        "provider": provider_display,
        "is_command": is_json_command,
        "action_data": parsed_action
    }

