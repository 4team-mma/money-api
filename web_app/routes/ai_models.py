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
from ..services.ollama_service import OllamaService     # 本地模型
from ..services.finance_agent_service import FinanceAgentService # 🆕 引入新大腦

from typing import Optional
import os
import time
import traceback
import httpx
from dotenv import load_dotenv
import json
import re

load_dotenv()
router = APIRouter()

# --- 1. 獲取配置 (保留完整的 API 文件說明) ---
@router.get(
    "/config", 
    response_model=Optional[AIConfigResponse],
    summary="取得 AI 模型配置",
    description="根據 provider 參數取得對應的設定；若未指定，則回傳目前生效 (is_active=True) 的設定。"
)
def get_ai_robot_config(
    provider: Optional[str] = Query(None, description="指定查詢的模型供應商 (gemini, ollama, anythingllm)"), 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    query = db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id)
    
    target_config = None
    if provider:
        # 查特定大腦的最新一筆
        target_config = query.filter(AIConfig.provider == provider).order_by(AIConfig.created_at.desc()).first()
    else:
        # 預設查目前生效中的
        target_config = query.filter(AIConfig.is_active == True).first()
        # 防呆：如果完全沒設定過，至少回傳一個預設值，避免前端壞掉
        if not target_config:
            # 嘗試找任一筆，或直接回傳 None 讓下方處理預設值
            target_config = query.first()

    if target_config:
        # 🚀 修正：先轉字典，再用解包方式建立，Pylance 絕對不會報錯
        data_dict = {
            "provider": str(target_config.provider),
            "base_url": target_config.base_url,
            "model_version": target_config.model_version, # 這裡就是解決選單空白的關鍵
            "system_prompt": target_config.system_prompt,
            "is_active": bool(target_config.is_active),
            "has_key": target_config.api_key is not None and target_config.api_key != "none"
        }
        return AIConfigResponse(**data_dict)
    
    # 若資料庫完全無資料，回傳預設結構
    return AIConfigResponse(
        provider="gemini",
        base_url="",
        model_version="gemini-1.5-flash",
        system_prompt="你是理財小助手喵喵...",
        is_active=False,
        has_key=False
    )

# --- 2. 儲存配置 (保留完整邏輯與錯誤處理) ---
@router.post(
    "/save", 
    summary="儲存或更新 AI 配置",
    description="儲存 API Key (自動加密)、切換生效模型，並更新 System Prompt。"
)
def save_ai_config(
    payload: AIConfigSave, 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    try:
        # 先將該使用者所有設定設為不生效 (單選邏輯)
        db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id).update({"is_active": False})
        
        # 決定金鑰：如果有傳入新 Key 就加密，否則嘗試抓取該 provider 舊有的 Key
        new_key = payload.api_key
        secured_key = "none"

        if new_key and new_key != "none" and new_key.strip():
            secured_key = encrypt_api_key(new_key)
        else:
            # 嘗試找舊的 Key 繼承使用
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
    summary="與 AI 喵喵對話",
    description="接收使用者訊息，透過智能篩選器判斷意圖，若為記帳則回傳 JSON 指令。"
)
async def chat_with_meow(
    req: ChatRequest, 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    start_time = time.time()
    db.expire_all() 

    # 1. 取得目前生效配置 (先看使用者自己有沒有特別設定)
    config = db.query(AIConfig).filter(
        AIConfig.user_id == current_user.user_id, 
        AIConfig.is_active == True
    ).first()

    # 🌟 核心新增：如果使用者沒設定，強制套用「管理員 (user_id=1)」的設定！
    if not config:
        config = db.query(AIConfig).filter(
            AIConfig.user_id == 1, 
            AIConfig.is_active == True
        ).first()

    # 防呆預設 (如果連管理員都沒設定)
    if not config:
        config = AIConfig(provider="gemini", model_version="gemini-1.5-flash", system_prompt="你是理財小助手喵喵喵")

    # 2. 🧠 呼叫大腦：獲取智能篩選後的財務上下文與意圖
    try:
        # 接收 dict 格式
        agent_response = FinanceAgentService.get_context(db, current_user.user_id, req.message)
        current_intent = agent_response["intent"]
        financial_context_instruction = agent_response["system_prompt"]
        print(f"🎯 [意圖偵測]: {current_intent}")
    except Exception as e:
        print(f"❌ 數據讀取失敗: {e}")
        current_intent = "CHAT"
        financial_context_instruction = "【系統訊息】暫時無法讀取財務資料，請依一般常識回答。"

    # 3. 組合最終指令 (使用者自訂 Prompt + 財務數據)
    final_system_prompt = f"{config.system_prompt}\n\n{financial_context_instruction}"

    # 4. 根據 Provider 分流呼叫
    try:
        reply = "喵喵不知道該說什麼..."
        actual_model_used = config.model_version  # 先給一個預設值
        
        if config.provider == "gemini":
            # 處理 Key 解密
            env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            db_key = "none"
            if config.api_key and config.api_key != "none":
                try:
                    db_key = decrypt_api_key(config.api_key)
                except: pass
            
            final_key = db_key if (db_key and len(db_key) > 10) else env_key
            if not final_key: raise Exception("找不到有效 API Key 喵！")

            # 🚀 接收字典格式的回傳值
            result = await GeminiService.chat_async(
                api_key=final_key,
                model_id=config.model_version,
                prompt=req.message,
                system_instruction=final_system_prompt
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
                    json={
                        "message": f"{final_system_prompt}\n問題：{req.message}", 
                        "mode": "chat"
                    }, 
                    headers={"Authorization": f"Bearer {any_key}"}, 
                    timeout=120.0
                )
                reply = res.json().get("textResponse", "喵... AnyThingLLM 沒回應。")
        else:
            reply = "喵喵目前不知道該用哪個大腦。"

        # ==========================================
        # 🌟 核心新增：JSON 指令解析防呆機制
        # ==========================================
        is_json_command = False
        parsed_action = None
        
        if current_intent == "RECORD":
            try:
                # 1. 先用 Regex 強制抓取 { } 之間的內容 (無視 AI 講的廢話)
                match = re.search(r'\{.*\}', reply.strip(), re.DOTALL)
                if match:
                    clean_json_str = match.group(0)
                    parsed_data = json.loads(clean_json_str)
                    
                    if parsed_data.get("action") == "confirm_record":
                        is_json_command = True
                        parsed_action = parsed_data
                        
                        # 2. 判斷文字顯示
                        r_type = parsed_data.get('record_type', 'expense')
                        action_word = "轉帳" if r_type == 'transfer' else "記錄"
                        item_word = parsed_data.get('note', '未知項目')
                        amt_word = parsed_data.get('amount', 0)
                        
                        reply = f"收到喵！小主人剛才說要{action_word}：{item_word} {amt_word} 元，請確認卡片喵！"
                else:
                    raise ValueError("找不到 JSON 格式的資料")

            except Exception as parse_err:
                print(f"⚠️ 解析 JSON 失敗，降級為一般文字顯示。錯誤: {parse_err}")
                is_json_command = False

        duration = round(time.time() - start_time, 2)
        print(f"✨ [AI DEBUG] 回應成功！耗時: {duration}s")
        
        # 🌟 核心保留：任務進度掃描
        from web_app.services.game_service import GameService
        try:
            GameService.update_mission_progress(
                db=db,
                user_id=current_user.user_id,
                category='AI_聊天',
                note=req.message,
                increment=1
            )
        except Exception as game_err:
            print(f"⚠️ 任務進度更新失敗: {game_err}")
        
        provider_display = f"gemini ({actual_model_used})" if config.provider == "gemini" else f"{config.provider} ({config.model_version})"
        
        # 回傳給前端
        return {
            "reply": reply, 
            "duration": duration, 
            "provider": provider_display,
            "is_command": is_json_command,    # 告訴前端是否要彈出卡片
            "action_data": parsed_action      # 前端卡片需要的變數
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "reply": f"喵... 系統連線失敗: {str(e)[:50]}", 
            "duration": 0, 
            "provider": config.provider,
            "is_command": False
        }