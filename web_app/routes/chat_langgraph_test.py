from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from web_app.database import get_db
from web_app.dependencies import get_current_user
from web_app.models.models import Member
# 匯入你剛寫好的超強函數
from web_app.services.advisor_graph_service import analyze_finance_advice

router = APIRouter()

@router.get("/test-喵喵顧問")
async def test_advisor(
    message: str = "喵喵，我做資訊軟體業，我 2026 年 4 月的薪水算高嗎？",
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    # 直接呼叫你的 LangGraph！
    reply = await analyze_finance_advice(user_message=message, db=db, current_user=current_user)
    return {"reply": reply}