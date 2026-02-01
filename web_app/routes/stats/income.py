from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from web_app.dependencies import get_db, get_current_user
from web_app.models.models import AddRecord, Account
from enum import Enum

router = APIRouter()


# 定義分組枚舉
class GroupField(str, Enum):
    category = "add_class"
    account = "account"
    member = "add_member"


@router.get("/category")
async def get_income_category_stats(
    start_date: date = Query(...),
    end_date: date = Query(...),
    group_by_field: GroupField = Query(GroupField.category),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # 1. 初始查詢物件（包含 Join）
    # 使用 outerjoin 以防萬一該記錄的 account_id 為空或找不到對應帳號
    query = db.query(func.sum(AddRecord.add_amount).label("total_amount")).outerjoin(
        Account, AddRecord.account_id == Account.account_id
    )

    # 2. 根據參數決定「顯示名稱」與「分組欄位」
    if group_by_field == GroupField.category:
        display_column = func.coalesce(AddRecord.add_class, "未分類").label(
            "display_name"
        )
        group_column = AddRecord.add_class

    elif group_by_field == GroupField.account:
        # 關鍵點：這裡我們改拿 Account 表的名稱，如果沒有名稱則顯示 "未知帳戶"
        display_column = func.coalesce(Account.account_name, "未知帳戶").label(
            "display_name"
        )
        group_column = Account.account_name  # 依據名稱分組

    elif group_by_field == GroupField.member:
        display_column = func.coalesce(AddRecord.add_member, "未指定成員").label(
            "display_name"
        )
        group_column = AddRecord.add_member

    # 3. 執行完整查詢
    results = (
        query.add_columns(display_column)
        .filter(
            AddRecord.user_id == current_user.user_id,
            AddRecord.add_type == True,  # 收入為 True
            AddRecord.add_date.between(start_date, end_date),
        )
        .group_by(group_column)
        .order_by(func.sum(AddRecord.add_amount).desc())
        .all()
    )

    # 4. 計算總額
    grand_total = sum(r.total_amount for r in results) or 0

    # 5. 格式化回傳
    return [
        {
            "id": index + 1,
            "category": r.display_name,
            "amount": float(r.total_amount),
            "ratio": (
                round((float(r.total_amount) / float(grand_total) * 100), 1)
                if grand_total > 0
                else 0
            ),
        }
        for index, r in enumerate(results)
    ]
