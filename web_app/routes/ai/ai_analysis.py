import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from web_app.dependencies import get_db, get_current_user
from web_app.services.gemini_service import GeminiService
from web_app.services.advisor_tools import FinancialAdvisorService
from web_app.prompts.ai_analysis_prompts import get_financial_analysis_prompt, SYSTEM_INSTRUCTION

router = APIRouter()

@router.get("/financial-insight")
async def get_financial_insight(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 1. 抓取包含 Z-score 異常偵測的數據
    # 這裡 financial_data 已經包含了 anomaly_analysis 欄位
    financial_data = await FinancialAdvisorService.get_ai_context(db, current_user)
    
    # 2. 生成 Prompt 
    # 💡 關鍵：妳的 get_financial_analysis_prompt 函式需要能處理新的資料結構
    prompt = get_financial_analysis_prompt(financial_data)
    
    # 3. 呼叫 Gemini
    env_key = os.getenv("GEMINI_API_KEY")
    db_key = None
    raw_key = db_key if (db_key and len(db_key) > 10) else env_key
    if not raw_key:
        raise HTTPException(
            status_code=500, 
            detail="系統設定異常：找不到有效的 Gemini API Key，請檢查資料庫設定或 .env 檔案。"
        )
    final_key: str = str(raw_key)
    result = await GeminiService.chat_async(
        api_key=final_key,
        model_id="gemini-1.5-flash",
        prompt=prompt,
        system_instruction=SYSTEM_INSTRUCTION
    )
    
    # 4. 回傳給前端
    # 建議把結構理清楚，方便前端 Vue 
    return {
        "ai_insight": result.get("text", "無法生成分析建議"), # AI 產生的建議文字
        "metrics": financial_data.get("metrics", {}),# 包含 total_expense, anomaly_analysis
        "top_categories": financial_data.get("top_categories", [])# 讓前端也能顯示圓餅圖或列表
    }
