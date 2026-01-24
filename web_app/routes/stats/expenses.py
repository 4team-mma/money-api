from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from web_app.dependencies import get_db, get_current_user
from web_app.models.models import AddRecord  # 🌟 修正：從 models 引入正確的類別名

router = APIRouter()

@router.get("/category")
async def get_expense_category_stats(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # 🌟 修正：使用 AddRecord 以及正確的欄位名稱 (add_class, add_amount, add_type)
    results = db.query(
        AddRecord.add_class.label("category"),
        func.sum(AddRecord.add_amount).label("total_amount")
    ).filter(
        AddRecord.user_id == current_user.user_id,
        AddRecord.add_type == False, # 支出為 False
        AddRecord.add_date >= start_date,
        AddRecord.add_date <= end_date
    ).group_by(AddRecord.add_class).order_by(func.sum(AddRecord.add_amount).desc()).all()

    # 計算總額
    grand_total = sum(r.total_amount for r in results)

    # 格式化回傳
    return [
        {
            "id": index + 1,
            "category": r.category if r.category else "未分類",
            "amount": float(r.total_amount),
            "ratio": round((float(r.total_amount) / float(grand_total) * 100), 1) if grand_total > 0 else 0
        }
        for index, r in enumerate(results)
    ]