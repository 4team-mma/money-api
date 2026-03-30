import os
import shutil
import pandas as pd
import logging
from fastapi import APIRouter, Depends, Body, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Member, IntentReviewLog 
from ...dependencies import get_current_user
from ...schemas.ai import AICompareResponse

# 引入雙 Service
from ...services.finance_agent_service import FinanceAgentService
from ...services.finance_agent_mixai_service import FinanceAgentMixAIService

router = APIRouter(tags=["AI 喵喵開發者工具"])
logger = logging.getLogger(__name__)

# --- 🎯 設定路徑 (完全依照你的最新設定) ---
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

# 3. 【執行批次測試】(補上 V1/V2 對比與 MySQL 寫入)
@router.post("/batch_run", summary="🏃 執行批次自動化測試")
async def batch_test_ai(
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    if current_user.role not in ["ai_test", "admin"]:
        raise HTTPException(status_code=403, detail="權限不足")

    # 優先序：暫存上傳檔 > 你指定的 temp/golden_test.xlsx
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
            
            # 同時跑 V1 與 V2 對比
            legacy_intent = FinanceAgentService.analyze_intent(msg)
            res = FinanceAgentMixAIService.analyze_intent(msg)
            
            is_correct = (res["final_intent"] == true_intent)
            if is_correct: correct_count += 1
            
            # 寫入 Review Log 用於未來重新訓練
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

            results.append({
                "review_id": new_log.review_id,
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

# 4. 【單句對比】
@router.post("/compare", response_model=AICompareResponse, summary="🎙️ 手動單句對比")
async def compare_ai_intent(
    message: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    if current_user.role not in ["ai_test", "admin"]:
        raise HTTPException(status_code=403, detail="權限不足")

    legacy_intent = FinanceAgentService.analyze_intent(message)
    mix_ai_res = FinanceAgentMixAIService.analyze_intent(message)
    
    new_log = IntentReviewLog(
        user_id=current_user.user_id,
        user_message=message,
        predicted_intent=mix_ai_res["final_intent"],
        confidence_score=mix_ai_res["confidence"]
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)

    return {
        "review_id": new_log.review_id,
        "legacy": {"intent": legacy_intent},
        "mix_ai": {
            "intent": mix_ai_res["final_intent"],
            "raw_ai_guess": mix_ai_res["predicted_intent"],
            "confidence": mix_ai_res["confidence"]
        }
    }

# 5. 【更新人工校正結果】
@router.put("/logs/{review_id}", summary="🛠️ 更新人工校正意圖")
async def update_intent_review(
    review_id: int,
    payload: dict = Body(...), # 接收 {"corrected_intent": "..."}
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    if current_user.role not in ["ai_test", "admin"]:
        raise HTTPException(status_code=403, detail="權限不足")

    # 找尋該筆紀錄
    log_entry = db.query(IntentReviewLog).filter(IntentReviewLog.review_id == review_id).first()
    if not log_entry:
        raise HTTPException(status_code=404, detail="找不到該筆紀錄喵！")

    # 更新校正內容與審核狀態
    corrected_intent = payload.get("corrected_intent")
    if corrected_intent:
        log_entry.corrected_intent = corrected_intent
        log_entry.is_reviewed = 1
        db.commit()
        return {"success": True, "message": f"序號 {review_id} 已修正為 {corrected_intent} 喵！"}
    
    raise HTTPException(status_code=400, detail="請提供正確的意圖名稱")