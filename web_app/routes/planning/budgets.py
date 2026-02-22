from fastapi import APIRouter, Depends, Query
from sqlalchemy import extract, func, and_
from sqlalchemy.orm import Session
from web_app.schemas.budgetBase import BudgetUpdate
from web_app.models.models import Budget, Member, AddRecord
from web_app.dependencies import get_db, get_current_user
from datetime import datetime

router = APIRouter()

# --- 1. 取得當月實際支出統計 ---
@router.get("/stats", summary="取得當月支出統計", description="統計當月各類別與標籤的總支出金額，用於與預算進行對比。")
def get_monthly_actual_stats(db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    """
    從收支紀錄 (AddRecord) 撈取本月資料：
    - **categories**: 各消費類別的總支出
    - **tags**: 各標籤的總支出
    """
    now = datetime.now()
    
    # 取得當月各類別支出總額
    class_stats = db.query(
        AddRecord.add_class,
        AddRecord.add_class_icon,
        func.sum(AddRecord.add_amount).label("spent")
    ).filter(
        and_(
            AddRecord.user_id == current_user.user_id,
            AddRecord.add_type == False,  # False 代表支出
            extract('year', AddRecord.add_date) == now.year,
            extract('month', AddRecord.add_date) == now.month
        )
    ).group_by(AddRecord.add_class, AddRecord.add_class_icon).all()

    # 取得當月各標籤支出總和
    tag_stats = db.query(
        AddRecord.add_tag,
        func.sum(AddRecord.add_amount).label("spent")
    ).filter(
        and_(
            AddRecord.user_id == current_user.user_id,
            AddRecord.add_type == False,
            extract('year', AddRecord.add_date) == now.year,
            extract('month', AddRecord.add_date) == now.month
        )
    ).group_by(AddRecord.add_tag).all()

    return {
        "categories": [
            {"name": s.add_class, "icon": s.add_class_icon or "💰", "spent": float(s.spent or 0)} 
            for s in class_stats
        ],
        "tags": [
            {"name": s.add_tag or "未分類", "spent": float(s.spent or 0)} 
            for s in tag_stats
        ]
    }

# --- 2. 取得所有預算設定 (總額/類別/標籤) ---
@router.get("/all", summary="取得所有預算設定", description="回傳目前登入使用者設定的所有預算清單（含類別預算與標籤預算）。")
def get_all_budgets(
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    budgets = db.query(Budget).filter(Budget.user_id == current_user.user_id).all()
    return budgets

# --- 3. 更新或新增預算 ---
@router.post("/batch", summary="批量更新或新增預算", description="接收一個清單，若該類別/標籤預算已存在則更新金額，不存在則新建。")
def batch_update_budgets(
    data_list: list[BudgetUpdate], 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    """
    這是一個 **Upsert** 操作 (Update or Insert)：
    - 比對 `user_id` + `category` + `tag`。
    - 成功後會回傳同步成功的筆數。
    """
    for data in data_list:
        query = db.query(Budget).filter(
            Budget.user_id == current_user.user_id,
            Budget.category == data.category,
            Budget.tag == data.tag
        )
            
        existing_budget = query.first()

        if existing_budget:
            existing_budget.amount = data.amount
            existing_budget.category_icon = data.category_icon
            existing_budget.tag_color = data.tag_color
            existing_budget.updated_at = datetime.now()
        else:
            new_budget = Budget(
                user_id=current_user.user_id,
                amount=data.amount,
                category=data.category,
                category_icon=data.category_icon,
                tag=data.tag,
                tag_color=data.tag_color
            )
            db.add(new_budget)
    
    db.commit()
    return {"status": "success", "message": f"成功同步 {len(data_list)} 筆預算設定"}

# --- 4. 刪除自定義類別預算 ---
@router.delete("/category", summary="刪除特定類別預算")
def delete_category_budget(
    category: str = Query(..., description="要刪除的類別名稱，例如：飲食"),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    budget = db.query(Budget).filter(
        Budget.user_id == current_user.user_id,
        Budget.category == category
    ).first()

    if budget:
        db.delete(budget)
        db.commit()
    return {"status": "success", "message": f"已刪除 {category} 預算"}

# --- 5. 刪除自定義標籤預算 ---
@router.delete("/tag", summary="刪除特定標籤預算")
def delete_tag_budget(
    tag: str = Query(..., description="要刪除的標籤名稱，例如：出差"),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    budget = db.query(Budget).filter(
        Budget.user_id == current_user.user_id,
        Budget.tag == tag
    ).first()

    if budget:
        db.delete(budget)
        db.commit()
        return {"status": "success", "message": f"已刪除標籤 {tag}"}
    
    return {"status": "not_found", "message": "找不到該預算紀錄"}
