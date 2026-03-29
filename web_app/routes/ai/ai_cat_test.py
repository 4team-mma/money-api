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

# --- 設定路徑 ---
TEMP_DIR = "web_app/temp/excel"
DEFAULT_TEST_FILE = "web_app/data/golden_test.xlsx"
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
    
    # 🌟 修正點：先檢查 filename 是否存在，再用 lower() 檢查副檔名
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

    # 儲存新檔案 (固定名稱方便 batch_run 讀取)
    try:
        with open(CURRENT_BATCH_FILE, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()

    return {"success": True, "message": f"測試檔 {file.filename} 上傳成功，已就緒喵！"}

# 2. 【清理暫存紀錄】
@router.delete("/clear_test_file", summary="🗑️ 清除暫存的測試檔")
async def clear_test_file(current_user: Member = Depends(get_current_user)):
    if current_user.role not in ["ai_test", "admin"]:
        raise HTTPException(status_code=403, detail="權限不足")
    
    if os.path.exists(CURRENT_BATCH_FILE):
        os.remove(CURRENT_BATCH_FILE)
        return {"success": True, "message": "暫存測試檔已刪除喵！"}
    return {"success": True, "message": "目前本來就沒有暫存檔喵。"}

# 3. 【執行批次測試】(升級雙兼容版)
@router.post("/batch_run", summary="🏃 執行批次自動化測試")
async def batch_test_ai(current_user: Member = Depends(get_current_user)):
    if current_user.role not in ["ai_test", "admin"]:
        raise HTTPException(status_code=403, detail="權限不足")

    # 優先序：暫存上傳檔 > 預設金牌檔
    file_path = CURRENT_BATCH_FILE if os.path.exists(CURRENT_BATCH_FILE) else DEFAULT_TEST_FILE
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="找不到任何測試集檔案 (請先上傳或檢查 web_app/data/ 喵！)")

    try:
        df = pd.read_excel(file_path)
        # 基本欄位檢查
        if 'text' not in df.columns or 'intent' not in df.columns:
            raise HTTPException(status_code=400, detail="Excel 必須包含 'text' 與 'intent' 欄位喵！")

        results = []
        correct_count = 0

        for _, row in df.iterrows():
            msg = str(row['text'])
            true_intent = str(row['intent'])
            
            # 跑 Mix AI 推論
            res = FinanceAgentMixAIService.analyze_intent(msg)
            
            is_correct = (res["final_intent"] == true_intent)
            if is_correct: correct_count += 1
            
            results.append({
                "text": msg,
                "true": true_intent,
                "pred": res["final_intent"],
                "is_correct": is_correct,
                "conf": res["confidence"]
            })

        accuracy = correct_count / len(df) if len(df) > 0 else 0
        source = "上傳檔案" if file_path == CURRENT_BATCH_FILE else "預設黃金測試集"
        
        return {
            "success": True,
            "source": source,
            "accuracy": accuracy,
            "total": len(df),
            "details": results
        }
    except Exception as e:
        logger.error(f"批次測試崩潰: {e}")
        raise HTTPException(status_code=500, detail=f"讀取 Excel 出錯: {str(e)}")

# 4. 【單句比對】(維持現狀，兩者兼容)
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
    
    # 存入 Review Log (用於後續 Human-in-the-loop)
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