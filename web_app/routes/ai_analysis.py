import os
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.gemini_service import GeminiService
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/cash-flow-summary")
async def get_cash_flow_summary(db: Session = Depends(get_db)):
    # 抓取妳 .env 裡的變數
    api_key = os.getenv("GOOGLE_API_KEY")
    
    # 模擬數據 (等週一討論完再寫 SQL)
    mock_data = "本月收入 55,000 元，支出 42,000 元，其中餐飲支出佔比 35% 最多。"
    
    system_instruction = "你是一位親切的理財顧問，請針對數據給出 50 字內的繁體中文建議。"
    
    # 呼叫同學寫好的 Service (這裡要用 await 因為他是非同步)
    result = await GeminiService.chat_async(
        api_key=api_key,
        model_id="gemini-1.5-flash",
        prompt=f"請分析這段數據：{mock_data}",
        system_instruction=system_instruction
    )
    
    return JSONResponse(
    content={"summary": result["text"]},
    headers={"Content-Type": "application/json; charset=utf-8"}
)