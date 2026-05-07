import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from web_app.dependencies import get_db, get_current_user
from web_app.services.gemini_service import GeminiService
from web_app.services.advisor_tools import FinancialAdvisorService
from web_app.prompts.ai_analysis_prompts import get_financial_analysis_prompt,SYSTEM_INSTRUCTION

router = APIRouter()

@router.get("/financial-insight")
async def get_financial_insight(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 1. 抓取數據 (已確認 Service 內包含 90天/80% 安檢門)
    financial_data = await FinancialAdvisorService.get_ai_context(db, current_user)

    # 💡 判斷是否解鎖
    if not financial_data.get("is_unlocked", False):
        return {
            "is_unlocked": False,
            "ai_insight": financial_data.get("message"),
            "status": financial_data.get("status"),
            "metrics": None
        }

    # 2. 生成分析 Prompt
    prompt = get_financial_analysis_prompt(financial_data)

    # 3. 呼叫 Gemini (優化 Key 抓取邏輯，刪除重複呼叫)
    final_key = os.getenv("GEMINI_API_KEY")
    if not final_key:
        # 這裡印在後端黑視窗，使用者看不到，只有開發者看得到
        print("CRITICAL ERROR: Gemini API Key is missing in .env file!")
        # 這裡回傳給前端
        raise HTTPException(
            status_code=500,
            detail="AI顧問目前有點斷線，請稍後再試或聯繫客服。"
        )

    # 這裡只呼叫一次就好！刪除原本代碼中重複的 result 賦值
    result = await GeminiService.chat_async(
        api_key=final_key,
        model_id="gemini-2.5-flash",
        prompt=prompt,
        system_instruction=SYSTEM_INSTRUCTION
    )

    # 4. 回傳完整分析給前端
    return {
        "is_unlocked": True,
        "ai_insight": result.get("text", "無法生成分析建議"),
        "metrics": financial_data.get("lifestyle_metrics", {}),
        "financial_summary": financial_data.get("financial_summary", {}),
        "consumption_structure": financial_data.get("consumption_structure", {})
    }