# web_app/routes/chat_langgraph_test.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from web_app.database import get_db
from web_app.dependencies import get_current_user
from web_app.models.models import Member
from web_app.services.advisor_graph_service import analyze_finance_advice

router = APIRouter()

@router.get("/test-advisor", summary="🧪 測試：LangGraph 專家獨立測試通道")
async def test_advisor(
    message: str = Query(
        "喵喵，我最近覺得花錢壓力很大，我的財務狀況還健康嗎？", 
        description="輸入想測試的問題，例如測試 Z-Score 或 CPI"
    ),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    """
    這個路由專門給工程師(你)在 Swagger UI 測試 LangGraph 專家大腦用的。
    前端 Vue 實際對話時不會呼叫這裡，而是呼叫統一的 /api/ai_models/chat。
    """
    # 直接呼叫你的 LangGraph！
    reply = await analyze_finance_advice(user_message=message, db=db, current_user=current_user)
    return {"reply": reply, "test_user": current_user.name}