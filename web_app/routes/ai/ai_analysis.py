import os
from fastapi import APIRouter, Depends
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
    api_key = os.getenv("GOOGLE_API_KEY")
    result = await GeminiService.chat_async(
        api_key=api_key,
        model_id="gemini-1.5-flash",
        prompt=prompt,
        system_instruction=SYSTEM_INSTRUCTION
    )
    
    # 4. 回傳給前端
    # 建議把結構理清楚，方便前端 Vue 渲染
    return {
        "ai_insight": result["text"],        # AI 產生的建議文字
        "metrics": financial_data["metrics"], # 包含 total_expense, anomaly_analysis 等
        "top_categories": financial_data["top_categories"] # 讓前端也能顯示圓餅圖或列表
    }