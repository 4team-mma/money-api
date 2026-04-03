import os
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from web_app.dependencies import get_db, get_current_user
from web_app.services.gemini_service import GeminiService
from web_app.services.advisor_tools import FinancialAdvisorService
from web_app.prompts.ai_analysis_prompts import get_financial_analysis_prompt, SYSTEM_INSTRUCTION

router = APIRouter()

@router.get("/financial-insight") # 建議改名，更貼合功能
async def get_financial_insight(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 1. 抓取真實數據
    financial_data = await FinancialAdvisorService.get_ai_context(db, current_user)

    # 2. 生成 Prompt
    prompt = get_financial_analysis_prompt(financial_data)

    # 3. 呼叫 Gemini
    api_key = os.getenv("GOOGLE_API_KEY")
    result = await GeminiService.chat_async(
        api_key=api_key,
        model_id="gemini-1.5-flash",
        prompt=prompt,
        system_instruction=SYSTEM_INSTRUCTION
    )

    return {"summary": result["text"], "raw_metrics": financial_data["metrics"]}
