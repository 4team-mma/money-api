from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from web_app.dependencies import get_db, get_current_user
from web_app.models.models import AddRecord, Account, Member
from collections import defaultdict
from enum import Enum
from typing import List
from web_app.schemas.expenses import ExpenseStatItem
router = APIRouter()


# 定義分組枚舉
class GroupField(str, Enum):
    category = "add_class"
    account = "account"
    member = "add_member"
    tag = "add_tag"

@router.get("/category", response_model=List[ExpenseStatItem], summary="📊 支出統計與占比分析")
async def get_expense_category_stats(
    start_date: date = Query(..., description="起始日期", examples=["2026-02-01"]),
    end_date: date = Query(..., description="結束日期", examples=["2026-02-28"]),
    group_by_field: GroupField = Query(
        GroupField.category,
        description="分組維度: category(分類), account(帳戶), member(成員), tag(標籤)"
        ),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """
    根據指定日期區間與維度，計算支出總額與佔比。常用於繪製圓餅圖。

    - **分組邏輯**:
        - **category**: 按消費分類（如：飲食、交通）。
        - **account**: 按支付帳戶（如：我的錢包、某銀行）。
        - **member**: 按消費者。
        - **tag**: 按標籤（支援「一筆紀錄多個標籤」的拆分計算）。
    
    - **標籤特殊處理**:
        - 若一筆 100 元紀錄含標籤 "A, B"，則 A 與 B 分類下都會計入 100 元，比例會重新依總額計算。
    """
    # 如果是按標籤分組，我們先查出所有含標籤的紀錄
    if group_by_field == GroupField.tag:
        # 查詢所有相關紀錄的標籤與金額
        records = db.query(AddRecord.add_tag, AddRecord.add_amount).filter(
            AddRecord.user_id == current_user.user_id,
            AddRecord.add_type == False,
            AddRecord.add_date.between(start_date, end_date),
        ).all()

        # 在 Python 中手動拆分與聚合
        tag_map = defaultdict(float)
        grand_total = 0
        for r in records:
            amount = float(r.add_amount or 0)
            grand_total += amount # 這是原始總額
            
            # 拆分標籤並去除前後空格
            tags = [t.strip() for t in (r.add_tag or "未分類標籤").split(",") if t.strip()]
            for t in tags:
                tag_map[t] += amount

        # 轉換成回傳格式並排序
        sorted_tags = sorted(tag_map.items(), key=lambda x: x[1], reverse=True)
        return [
            {
                "id": i + 1,
                "category": name,
                "amount": amt,
                "ratio": round((amt / grand_total * 100), 1) if grand_total > 0 else 0
            } for i, (name, amt) in enumerate(sorted_tags)
        ]

    # --- 若非標籤分組，則執行原本的 SQLAlchemy 聚合邏輯 ---
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
            AddRecord.add_type == False,  # 支出為 False
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
