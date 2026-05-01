# web_app/routes/ai_models.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import AIConfig, Member, AddRecord, Account
from ..schemas.ai import AIConfigSave, AIConfigResponse, ChatRequest
from ..dependencies import get_current_user,admin_required
from ..utils.ai_security import decrypt_api_key, encrypt_api_key

# 引入服務層 (Services)
from ..services.gemini_service import GeminiService
from ..services.ollama_service import OllamaService
from ..services.finance_agent_service import FinanceAgentService
from ..services.groq_service import GroqService
from ..services.advisor_graph_service import analyze_finance_advice

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
SYS_OLLAMA_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "gemma4:e4b")
SYS_GEMINI_MODEL = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-3-flash-preview")
AI_BRAIN_VERSION = os.getenv("AI_BRAIN_VERSION", "v1")

# 🌟 全域變數：輕量級對話狀態鎖 (Format: {user_id: expire_timestamp})
ADVISOR_STATE_LOCKS = {}


def get_sys_default_model(provider: str) -> str:
    """根據 Provider 決定預設模型名稱"""
    return SYS_OLLAMA_MODEL if provider == "ollama" else SYS_GEMINI_MODEL

# 👇 新增這個打工仔函數 👇
def get_user_history_for_prompt(db: Session, user_id: int) -> dict:
    """從資料庫撈取使用者專屬的：分類、標籤、成員、帳戶"""
    
    # 1. 處理分類 (Categories)
    base_cats = ["🍔 飲食", "🚗 交通", "🏠 居家", "🎮 娛樂", "💰 工資", "🏦 獎金", "🐷 投資"]
    try:
        history_cats = db.query(AddRecord.add_class_icon, AddRecord.add_class)\
                         .filter(AddRecord.user_id == user_id).distinct().all()
        custom_cats = [f"{icon} {name}" for icon, name in history_cats if icon and name]
    except:
        custom_cats = []
    all_cats = ", ".join(set(base_cats + custom_cats))

    # 2. 處理標籤 (Tags)
    base_tags = ["需要", "想要", "旅遊"]
    try:
        history_tags = db.query(AddRecord.add_tag)\
                         .filter(AddRecord.user_id == user_id).distinct().all()
        custom_tags = []
        for (tag_str,) in history_tags:
            if tag_str:
                custom_tags.extend(tag_str.split('/')) 
    except:
        custom_tags = []
    all_tags = ", ".join(set(base_tags + custom_tags))

    # 3. 處理成員 (Members)
    base_members = ["自己"]
    try:
        history_members = db.query(AddRecord.add_member)\
                            .filter(AddRecord.user_id == user_id).distinct().all()
        custom_members = [m[0] for m in history_members if m[0]]
    except:
        custom_members = []
    all_members = ", ".join(set(base_members + custom_members))

    # 🌟 4. 處理帳戶 (Accounts) - 動態抓取第一順位
    try:
        # 去帳戶表撈出這個小主人的所有帳戶名稱，用 created_at 排序確保第一個是最早建立的
        user_accounts = db.query(Account.account_name)\
                          .filter(Account.user_id == user_id)\
                          .order_by(Account.created_at.asc()).all()
        account_names = [a[0] for a in user_accounts if a[0]]
        
        if account_names:
            accounts_str = ", ".join(account_names)
            default_account = account_names[0]  # 直接拿陣列的第一個，也就是最早建立的帳戶
        else:
            accounts_str = "現金" # 系統保底防呆
            default_account = "現金"
    except Exception as e:
        print(f"❌ 撈取帳戶失敗：{e}")
        accounts_str = "現金"
        default_account = "現金"

    # 回傳打包好的四種清單
    return {
        "categories": all_cats,
        "tags": all_tags,
        "members": all_members,
        "accounts": accounts_str,
        "default_account": default_account
    }




# --- 1. 獲取配置 ---
@router.get(
    "/config",
    response_model=Optional[AIConfigResponse],
    summary="取得 AI 模型配置"
)
def get_ai_robot_config(
    provider: Optional[str] = Query(None, description="指定查詢的模型供應商"),
    db: Session = Depends(get_db),
    current_admin: Member = Depends(admin_required)
):
    query = db.query(AIConfig).filter(AIConfig.user_id == current_admin.user_id)

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
    current_admin: Member = Depends(admin_required)
):
    try:
        db.query(AIConfig).filter(AIConfig.user_id == current_admin.user_id).update({"is_active": False})

        new_key = payload.api_key
        secured_key = "none"

        if new_key and new_key != "none" and new_key.strip():
            secured_key = encrypt_api_key(new_key)
        else:
            old = db.query(AIConfig).filter(
                AIConfig.user_id == current_admin.user_id,
                AIConfig.provider == payload.provider
            ).order_by(AIConfig.created_at.desc()).first()
            if old and old.api_key:
                secured_key = old.api_key

        new_config = AIConfig(
            user_id=current_admin.user_id,
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
    
    
    # ==========================================
    # 🌟 狀態鎖檢測：如果被鎖定，直接強制進入 ADVISOR！
    # ==========================================
    is_locked = False
    current_intent = None
    
    if current_user.user_id in ADVISOR_STATE_LOCKS:
        # 檢查鎖是否過期 (設定 3 分鐘 = 180 秒)
        if time.time() < ADVISOR_STATE_LOCKS[current_user.user_id]:
            is_locked = True
            current_intent = "ADVISOR"
            financial_context_instruction = "【系統訊息】進入連續理財對話模式。"
            agent_response = {"intent": "ADVISOR", "confidence": 1.0, "is_cached": False}
            logger.info(f"🔒 [State Lock] 攔截成功！User {current_user.user_id} 強制進入 ADVISOR")
        else:
            # 鎖過期了，刪除並正常走意圖判斷
            del ADVISOR_STATE_LOCKS[current_user.user_id]
            logger.info(f"🔓 [State Lock] User {current_user.user_id} 鎖定超時，已解除。")

    # 4. 如果沒有鎖定，才去跑原本的 VectorDB 與 ONNX
    if not is_locked:
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
    actual_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    actual_model_used = config.model_version
    
    actual_provider_used = config.provider


    # ==========================================
    # 5. 意圖分流處理
    # ==========================================
    
    
    if current_intent in ["RECORD", "MULTI_RECORD"]:
        
        # 🌟🌟🌟 全面升級：動態注入分類、標籤、成員 🌟🌟🌟
        user_history = get_user_history_for_prompt(db, current_user.user_id)
        dynamic_rule = (
            f"\n\n【🚨 極度重要：小主人的專屬資料庫】\n"
            f"1. [專屬分類庫]：{user_history['categories']}\n"
            f"2. [常用標籤庫]：{user_history['tags']} (若有多個請用 '/' 分隔)\n"
            f"3. [常用成員庫]：{user_history['members']}\n"
            f"4. [常用帳戶庫]：{user_history['accounts']}\n"
            f"5. [預設帳戶]：{user_history['default_account']}\n"
            
            f"\n⚠️ [帳戶提取鐵律]：\n"
            f"- 若對話提到 [常用帳戶庫] 中的任何名稱（如：存入國泰、用中信付），\n"
            f"  [account_name] 必須強制填入該帳戶名稱！不可使用預設帳戶！\n"
            f"- 只有當對話完全沒提到任何帳戶時，[account_name] 才可填入「{user_history['default_account']}」。\n"
            
            f"\n⚠️ [標籤提取鐵律]：\n"
            f"- 除非小主人明確說出標籤名稱（如：標記為想要、這筆是旅遊），\n"
            f"- 否則 [add_tag] 必須保持空字串 \"\"，絕對禁止自行猜測情緒！\n"
            
            f"\n請務必優先從清單挑選正確名稱，並僅輸出 JSON 陣列喵！\n"
        )
        record_system_prompt = final_system_prompt + dynamic_rule
        # 🌟🌟🌟 新增結束 🌟🌟🌟
        
        
        # 🚀 通道 A：記帳 (強制走 Groq)
        try:
            groq_result = FinanceAgentService.execute_record_chain(record_system_prompt, latest_query)
            is_json_command = True
            
            raw_action_data = groq_result.get("action_data", [])
            # 建立一個「名字 -> ID」的對照表，方便等等快速轉換
            user_accounts = db.query(Account).filter(Account.user_id == current_user.user_id).all()
            account_map = {acc.account_name: acc.account_id for acc in user_accounts}
            
            # 取得預設帳戶 ID (保底用)
            default_acc_id = None
            if user_accounts:
                # 拿第一個帳戶當預設 (對應你 get_user_history_for_prompt 的邏輯)
                default_acc_id = user_accounts[0].account_id

            # 🌟 進行資料補強 (Data Enrichment)
            for record in raw_action_data:
                
                if record.get("record_type") == "income" and record.get("to_account"):
                    if record["to_account"] in account_map:
                        record["account_name"] = record["to_account"]
                
                # 1. 帳戶轉換：名字變 ID
                acc_name = record.get("account_name")
                if acc_name in account_map:
                    record["account_id"] = account_map[acc_name]
                else:
                    record["account_id"] = default_acc_id  # 找不到就用預設
                
                # 2. 標籤補強：如果 AI 給空字串或沒給，補上「需要」
                if not record.get("add_tag") or record["add_tag"].strip() == "":
                    record["add_tag"] = "需要"
                
                # 3. 成員補強：如果沒抓到，補上「自己」
                if not record.get("add_member"):
                    record["add_member"] = "自己"
            
            parsed_action = groq_result.get("action_data", {})
            reply = groq_result.get("reply_text", "已記好囉喵！")
            
            actual_model_used = "Groq (Llama-Record)"
            actual_provider_used = "groq"  # 🌟 補上這行：強制標記為 groq
            # token
            actual_usage = groq_result.get("usage", actual_usage)
            
        except Exception as e:
            logger.error(f"Groq 解析 JSON 失敗: {str(e)}")
            reply = "喵喵聽不懂這筆帳，請換個方式說喵！"
            
            
    
    # 🌟🌟🌟 ADVISOR 專屬通道 🌟🌟🌟
    elif current_intent == "ADVISOR":
        try:
            # 🌟 修正點 1：用 advisor_res 來接住字典！
            advisor_res = await analyze_finance_advice(
                user_message=latest_query,
                db=db,
                current_user=current_user
            )
            
            # 🌟 修正點 2：從字典中拆解出對話內容與 Token 帳單
            reply = advisor_res["content"]
            actual_usage = advisor_res["usage"]
            
            is_json_command = False
            actual_model_used = "Groq (LangGraph-Advisor)"
            actual_provider_used = "groq"
            
            # ==========================================
            # 🌟 判斷是否需要「繼續上鎖」
            # ==========================================
            if any(q in reply for q in ["？", "?", "請問", "告訴我", "你的行業是"]):
                ADVISOR_STATE_LOCKS[current_user.user_id] = time.time() + 180
            else:
                if current_user.user_id in ADVISOR_STATE_LOCKS:
                    del ADVISOR_STATE_LOCKS[current_user.user_id]
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            reply = "喵喵的理財大腦暫時有點打結，請稍後再試喵！"
            actual_model_used = "Error"
            if current_user.user_id in ADVISOR_STATE_LOCKS:
                del ADVISOR_STATE_LOCKS[current_user.user_id]
    # 🌟🌟🌟 新增結束 🌟🌟🌟
    
    
            

    else:
        # 💡 通道 B：其他意圖
        try:
            # 🌟 邏輯：如果在 Render 且是 QUERY 意圖，自動導向 Groq 70B
            active_provider = config.provider
            active_model = config.model_version
            
            # 🌟 新增：準備一把專用的備用鑰匙
            override_api_key = None 

            if current_intent == "QUERY" and is_on_render:
                active_provider = "groq"
                # llama-3.3-70b-versatile
                active_model = "meta-llama/llama-4-scout-17b-16e-instruct"
                # 🌟 致命修復：既然強制換腦，就必須強制從環境變數拿 Groq 的鑰匙！
                override_api_key = os.getenv("GROQ_API_KEY") 
                print(f"🚀 [雲端優化] QUERY 自動切換至 Groq 70B")
                
                
            # ==========================================
            # 🌟 終極防護：根據「意圖」嚴格派發工具 (動態掛載)
            # ==========================================
            from ..services.finance_tools import get_budget_tool, search_manual_tool
            from ..services.notion_mcp_service import create_notion_tool
            notion_tool = create_notion_tool(db, current_user)
            
            active_tools = [] # 預設空手，什麼工具都不給！
            
            # 只有知識查詢，才給手冊工具
            if current_intent in ["KNOWLEDGE", "MULTI_KNOWLEDGE"]:
                active_tools.append(search_manual_tool)
                
            # 只有財務查詢，才給預算工具
            elif current_intent in ["QUERY", "MULTI_QUERY"]:
                active_tools.append(get_budget_tool)

            # 外部 MCP 工具獨立判斷
            if "notion" in latest_query.lower() or "同步" in latest_query:
                active_tools.append(notion_tool)
            # ==========================================

            # A. Gemini 處理
            if active_provider == "gemini":
                env_key = os.getenv("GEMINI_API_KEY") 
                db_key = decrypt_api_key(config.api_key) if config.api_key and config.api_key != "none" else None
                f_key = override_api_key or db_key or env_key
                if not f_key: raise Exception("Missing Key")

                res = await GeminiService.chat_async(
                    api_key=str(f_key), model_id=active_model,
                    prompt=f"【機密 user_id: {current_user.user_id}】\n問題：{req.message}",
                    system_instruction=final_system_prompt,
                    # 🌟 這裡修改：如果陣列是空的，就傳 None，直接沒收工具！
                    tools=active_tools if active_tools else None 
                )
                reply = res["text"]
                actual_model_used = res["actual_model"]
                # 🌟 關鍵：把 Gemini 的帳單交給你的 Token Radar 變數
                actual_usage = res.get("usage", actual_usage)


            # B. Groq 處理
            elif active_provider == "groq":
                env_key = os.getenv("GROQ_API_KEY")
                db_key = decrypt_api_key(config.api_key) if config.api_key and config.api_key != "none" else None
                f_key = override_api_key or db_key or env_key
                if not f_key: raise Exception("Missing Key")

                # 🌟 核心修正：用 res 接住字典，並把真實 token 數據挖出來
                res = await GroqService.chat_async(
                    api_key=str(f_key), model_id=active_model,
                    prompt=req.message, system_instruction=final_system_prompt
                )
                reply = res["text"]
                actual_model_used = active_model
                actual_usage = res.get("usage", actual_usage)

            # C. Ollama 處理
            elif active_provider == "ollama":
                if is_on_render:
                    reply = "雲端環境暫不支援 Ollama，請手動切換至 Gemini 或 Groq 喵。"
                else:
                    reply = await OllamaService.chat_async(
                        base_url=str(config.base_url or "http://localhost:11434"),
                        model_id=active_model,
                        prompt=req.message,
                        system_instruction=final_system_prompt,
                        tools=active_tools if active_tools else None
                    )

        except Exception as e:
            logger.error(f"AI Chat Error: {str(e)}", exc_info=True)
            reply = f"連線失敗喵... ({str(e)})"
            
            

# 🌟 核心新增：終極物理淨化器！強制消除小模型傲嬌的對話前綴
    if isinstance(reply, str):
        import re
        # 這把正則手術刀，會把開頭所有的「喵喵：」、「喵喵：喵喵：」一次切除得乾乾淨淨
        reply = re.sub(r"^((喵喵|小助手|Money\s*喵)[：:\s]*)+", "", reply).strip()


            
    # ==========================================
    # 🌟 核心新增：將消耗數據寫入 Token 監測雷達 (正義喵喵誠實版)
    # ==========================================
    try:
        from ..models import TokenUsageLog
        
        # 1. 取得剛剛一路傳過來的快取狀態
        is_sql_cached = agent_response.get("is_cached", False)
        sql_usage = agent_response.get("sql_usage", {}) # 🌟 拿到 SQL 引擎傳過來的帳單！
        
        # 2. 拿取絕對真實的 API 數據
        p_tokens = actual_usage.get("prompt_tokens", 0) + sql_usage.get("prompt_tokens", 0)
        c_tokens = actual_usage.get("completion_tokens", 0) + sql_usage.get("completion_tokens", 0)
        t_tokens = actual_usage.get("total_tokens", 0) + sql_usage.get("total_tokens", 0)
        
        # 3. 🌟 正義審判：徹底刪除造假邏輯！是 0 就是 0！
        # 並且在 Snippet 前面加上誠實的標籤，讓小主人一眼看穿真相
        snippet_prefix = ""
        model_display = actual_model_used or "unknown"

        # 👇 核心補回：就是這兩行被我誤刪了！把背後代工的高難度任務帳單，強制寄給 Groq！
        if current_intent in ["RECORD", "MULTI_RECORD", "ADVISOR", "QUERY", "MULTI_QUERY"]:
            actual_provider_used = "groq"

        if is_sql_cached:
            # 真實的快取命中：保證 0 消耗
            p_tokens, c_tokens, t_tokens = 0, 0, 0
            snippet_prefix = "⚡[快取命中] "
            model_display = "1.5F Semantic Cache" # 在雷達上自豪地秀出這是快取的功勞！
        elif t_tokens == 0:
            # 沒命中快取，但 Token 卻是 0：老實承認 API 沒回傳或斷線
            snippet_prefix = "⚠️[API未回傳] "

        # 4. 寫入資料庫 (絕無假帳)
        token_log = TokenUsageLog(
            user_id=current_user.user_id,
            provider=actual_provider_used,
            model_version=model_display,
            intent_type=current_intent,
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
            total_tokens=t_tokens,
            latency_ms=int((time.time() - start_time) * 1000),
            is_cached=is_sql_cached,
            request_snippet=f"{snippet_prefix}[User {current_user.user_id}] {latest_query}"[:500] 
        )
        db.add(token_log)
        db.commit()
    except Exception as e:
        logger.error(f"❌ Token 雷達紀錄失敗: {str(e)}")
        db.rollback()
    # ==========================================
    # ==========================================

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
    # 🌟 核心新增：自動將對話存入「意圖審核日誌」(信心度 < 0.8 才存)
    # ==========================================
    conf_val = agent_response.get("confidence", 1.0)
    
    # 只有信心度低於 0.8 (代表 AI 不太確定) 才自動觸發紀錄
    if conf_val < 0.8:
        try:
            from ..models import IntentReviewLog
            from decimal import Decimal

            new_review_log = IntentReviewLog(
                user_id=current_user.user_id,
                user_message=latest_query,
                predicted_intent=current_intent,
                confidence_score=Decimal(str(conf_val)),
                llm_response=reply,
                is_reviewed=0
            )
            db.add(new_review_log)
            db.commit() 
            print(f"⚠️ [觸發紀錄] 信心度 {conf_val} < 0.8，已寫入審核日誌！")
        except Exception as log_err:
            logger.error(f"❌ 寫入對話審核日誌失敗: {str(log_err)}")
            db.rollback()
    # ==========================================

    provider_display = f"gemini ({actual_model_used})" if config.provider == "gemini" and current_intent != "RECORD" else actual_model_used

    return {
        "reply": reply,
        "duration": duration,
        "provider": provider_display, # 👈 這裡依然回傳原本的設定給 Vue
        "is_command": is_json_command,
        "action_data": parsed_action,
        "intent": current_intent,  # 🌟 新增：傳給前端
        "confidence": conf_val     # 🌟 新增：傳給前端
    }

