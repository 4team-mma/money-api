# web_app/routes/stats/trends.py
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from datetime import date
import logging

# 引入你的資料庫組件與模型
from web_app.database import get_db
from web_app.models.models import AddRecord, Member
from web_app.dependencies import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/cash-flow")
async def get_cash_flow_trend(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    try:
        # 1. 取得使用者 ID
        u_id = current_user.user_id

        # 2. 執行查詢
        # 🌟 關鍵修正：將 case([(條件, 值)], else_=0) 改為 case((條件, 值), else_=0)
        # 也就是拿掉中括號 []，直接傳入元組
        results = db.query(
            AddRecord.add_date.label("row_date"),
            func.sum(case((AddRecord.add_type == True, AddRecord.add_amount), else_=0)).label("income"),
            func.sum(case((AddRecord.add_type == False, AddRecord.add_amount), else_=0)).label("expense")
        ).filter(
            AddRecord.user_id == u_id,
            AddRecord.add_date >= start_date,
            AddRecord.add_date <= end_date
        ).group_by(
            AddRecord.add_date
        ).order_by(
            AddRecord.add_date.asc()
        ).all()

        # 3. 格式化回傳 (將 Decimal 轉為 float 避免 JSON 報錯)
        formatted_data = []
        for r in results:
            formatted_data.append({
                "date": r.row_date.strftime("%Y-%m-%d"),
                "income": float(r.income or 0),
                "expense": float(r.expense or 0),
                "net": float((r.income or 0) - (r.expense or 0))
            })

        return formatted_data

    except Exception as e:
        logger.error(f"趨勢 API 錯誤: {str(e)}")
        # 將具體錯誤傳回前端方便除錯
        raise HTTPException(status_code=500, detail=str(e))