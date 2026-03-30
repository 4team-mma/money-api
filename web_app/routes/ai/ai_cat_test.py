import os
import shutil
import pandas as pd
import logging
import asyncio
from fastapi import APIRouter, Depends, Body, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from ...database import get_db
from ...models import Member, IntentReviewLog, AIConfig  # 🌟 新增 AIConfig
from ...dependencies import get_current_user
from ...schemas.ai import AICompareResponse

# 引入雙 Service
from ...services.finance_agent_service import FinanceAgentService
from ...services.finance_agent_mixai_service import FinanceAgentMixAIService

# 🌟 引入所有需要的 LLM 服務與加密工具
from ...services.gemini_service import GeminiService
from ...services.ollama_service import OllamaService
from ...utils.ai_security import decrypt_api_key

# 引入你的警衛室
from web_app.utils.security_guard import is_malicious

router = APIRouter(tags=["AI 喵喵開發者工具"])
logger = logging.getLogger(__name__)

# --- 🎯 設定路徑 ---
TEMP_DIR = "web_app/temp/excel"
DEFAULT_TEST_FILE = "web_app/temp/excel/golden_test.xlsx" 
CURRENT_BATCH_FILE = os.path.join(TEMP_DIR, "current_test_batch.xlsx")

def ensure_temp_dir():
    """確保暫存目錄存在"""
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR, exist_ok=True)

# 1. 【上傳測試檔】
@router.post("/upload_test_file", summary="📤 上傳自定義測試 Excel")
async def upload_test_file(
    file: UploadFile = File(...),
    current_user: Member = Depends(get_current_user)
):
    if current_user.role not in ["ai_test", "admin"]:
        raise HTTPException(status_code=403, detail="權限不足")
    
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="僅支援 .xlsx 格式喵！")

    ensure_temp_dir()

    # 🔄 自動替換邏輯：先清空舊的
    for f in os.listdir(TEMP_DIR):
        file_path = os.path.join(TEMP_DIR, f)
        try:
            if os.path.isfile(file_path): os.unlink(file_path)
        except Exception as e:
            logger.error(f"清理舊檔失敗: {e}")

    try:
        with open(CURRENT_BATCH_FILE, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()

    return {"success": True, "message": f"測試檔 {file.filename} 上傳成功！"}

# 2. 【清理暫存紀錄】
@router.delete("/clear_test_file", summary="🗑️ 清除暫存的測試檔")
async def clear_test_file(current_user: Member = Depends(get_current_user)):
    if current_user.role not in ["ai_test", "admin"]:
        raise HTTPException(status_code=403, detail="權限不足")
    
    if os.path.exists(CURRENT_BATCH_FILE):
        os.remove(CURRENT_BATCH_FILE)
        return {"success": True, "message": "暫存測試檔已刪除喵！"}
    return {"success": True, "message": "目前沒有暫存檔。"}

# 3. 【執行批次測試】(阻絕重複寫入版)
@router.post("/batch_run", summary="🏃 執行批次自動化測試")
async def batch_test_ai(
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    if current_user.role not in ["ai_test", "admin"]:
        raise HTTPException(status_code=403, detail="權限不足")

    base_dir = os.getcwd()
    file_path = os.path.join(base_dir, CURRENT_BATCH_FILE) if os.path.exists(CURRENT_BATCH_FILE) else os.path.join(base_dir, DEFAULT_TEST_FILE)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"找不到測試集！請確認路徑 {DEFAULT_TEST_FILE} 存在喵！")

    try:
        df = pd.read_excel(file_path)
        results = []
        correct_count = 0

        for _, row in df.iterrows():
            msg = str(row['text'])
            true_intent = str(row['intent'])
            
            legacy_intent = FinanceAgentService.analyze_intent(msg)
            res = FinanceAgentMixAIService.analyze_intent(msg)
            
            is_correct = (res["final_intent"] == true_intent)
            if is_correct: correct_count += 1
            
            # 🌟 阻絕重複資料：去資料庫查有沒有這句話
            existing_log = db.query(IntentReviewLog).filter(IntentReviewLog.user_message == msg).first()
            
            if existing_log:
                # 如果有，就只更新預測結果，不新增！
                existing_log.predicted_intent = res["final_intent"]
                existing_log.confidence_score = res["confidence"]
                if not existing_log.is_reviewed and is_correct:
                    existing_log.corrected_intent = true_intent
                    existing_log.is_reviewed = 1
                
                review_id_to_use = existing_log.review_id
            else:
                # 如果沒有，才建立全新的資料
                new_log = IntentReviewLog(
                    user_id=current_user.user_id,
                    user_message=msg,
                    predicted_intent=res["final_intent"],
                    confidence_score=res["confidence"],
                    corrected_intent=true_intent if is_correct else None,
                    is_reviewed=1 if is_correct else 0
                )
                db.add(new_log)
                db.flush() 
                review_id_to_use = new_log.review_id

            results.append({
                "review_id": review_id_to_use,
                "text": msg,
                "true": true_intent,
                "legacy_pred": legacy_intent,
                "pred": res["final_intent"],
                "is_correct": is_correct,
                "conf": res["confidence"],
                "correction": true_intent
            })

        db.commit()
        accuracy = correct_count / len(df) if len(df) > 0 else 0
        
        return {
            "success": True,
            "source": "自定義" if "current_test_batch" in file_path else "預設黃金集",
            "accuracy": accuracy,
            "total": len(df),
            "details": results
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 4. 【單句對比】(🌟 已完美整合動態讀取後台 AI 模型)
@router.post("/compare", response_model=None, summary="🎙️ 手動單句對比")
async def compare_ai_intent(
    message: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    if current_user.role not in ["ai_test", "admin"]:
        raise HTTPException(status_code=403, detail="權限不足")

    # 🛡️ 【第一關：警衛室攔截】
    if is_malicious(message):
        return {
            "review_id": None, 
            "legacy": {
                "intent": "BLOCKED",
                "response": "🚨 喵喵聽不懂這個奇怪的指令喔！(已被警衛攔截)"
            },
            "mix_ai": {
                "intent": "BLOCKED",
                "confidence": 1.0,
                "response": "🚨 喵喵聽不懂這個奇怪的指令喔！(已被警衛攔截)"
            }
        }

    # 🧠 【第二關：大腦意圖識別】
    legacy_intent = FinanceAgentService.analyze_intent(message)
    mix_ai_res = FinanceAgentMixAIService.analyze_intent(message)
    final_mix_intent = mix_ai_res["final_intent"]
    
    # 將正常預測寫入資料庫
    new_log = IntentReviewLog(
        user_id=current_user.user_id,
        user_message=message,
        predicted_intent=final_mix_intent,
        confidence_score=mix_ai_res["confidence"]
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)

    # 🌟 動態讀取當前使用者的 AI 配置 (跟真實聊天室邏輯一致)
    config = db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id, AIConfig.is_active == True).first()
    if not config: # 找不到就借用 user 1 的預設設定
        config = db.query(AIConfig).filter(AIConfig.user_id == 1, AIConfig.is_active == True).first()

    # 防呆：如果連 user 1 都沒有，給個硬核預設值
    provider = config.provider if config else "gemini"
    model_version = config.model_version if config else "gemini-3-flash-preview"
    base_url = config.base_url if config else "http://localhost:11434"

    # 👄 【第三關：嘴巴產生實際回覆 (依據後台動態選擇模型)】
    async def get_ai_reply_by_intent(target_intent: str, user_text: str) -> str:
        context_data = await FinanceAgentService.get_context(
            db=db, user=current_user, message=user_text, override_intent=target_intent
        )
        system_prompt = context_data["system_prompt"]
        
        try:
            if provider == "ollama":
                # 🦙 呼叫 Ollama
                reply = await OllamaService.chat_async(
                    base_url=base_url,
                    model_id=model_version,
                    prompt=user_text,
                    system_instruction=system_prompt
                )
                return f"[Ollama - {model_version}]\n{reply}"
                
            elif provider == "gemini":
                # ✨ 呼叫 Gemini
                env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                db_key = "none"
                if config and config.api_key and config.api_key != "none":
                    try:
                        db_key = decrypt_api_key(config.api_key)
                    except: pass
                
                final_key = db_key if (db_key and len(db_key) > 10) else env_key
                if not final_key: 
                    return "測試環境缺少 Gemini API Key"
                
                result = await GeminiService.chat_async(
                    api_key=final_key,
                    model_id=model_version,
                    prompt=user_text,
                    system_instruction=system_prompt
                )
                return f"[Gemini - {model_version}]\n{result['text']}"
                
            else:
                return f"尚未支援 {provider} 的測試回覆喵~"

        except Exception as e:
            return f"[{provider} 生成失敗]: {str(e)}"

    # 產生雙邊回覆 (同時並行處理，節省時間)
    legacy_response, mix_ai_response = await asyncio.gather(
        get_ai_reply_by_intent(legacy_intent, message),
        get_ai_reply_by_intent(final_mix_intent, message)
    )

    return {
        "review_id": new_log.review_id,
        "legacy": {
            "intent": legacy_intent,
            "response": legacy_response
        },
        "mix_ai": {
            "intent": final_mix_intent,
            "raw_ai_guess": mix_ai_res["predicted_intent"],
            "confidence": mix_ai_res["confidence"],
            "response": mix_ai_response
        }
    }

# 5. 【更新人工校正結果】
@router.put("/logs/{review_id}", summary="🛠️ 更新人工校正意圖")
async def update_intent_review(
    review_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    if current_user.role not in ["ai_test", "admin"]:
        raise HTTPException(status_code=403, detail="權限不足")

    log_entry = db.query(IntentReviewLog).filter(IntentReviewLog.review_id == review_id).first()
    if not log_entry:
        raise HTTPException(status_code=404, detail="找不到該筆紀錄喵！")

    corrected_intent = payload.get("corrected_intent")
    if corrected_intent:
        log_entry.corrected_intent = corrected_intent
        log_entry.is_reviewed = 1
        db.commit()
        return {"success": True, "message": f"序號 {review_id} 已修正為 {corrected_intent} 喵！"}
    
    raise HTTPException(status_code=400, detail="請提供正確的意圖名稱")