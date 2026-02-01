from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, union_all, literal_column
from ..database import get_db
from ..models import Account, AddRecord, Transaction
from ..schemas.dashboard import DashboardResponse, AccountBrief

router = APIRouter()

@router.get("/dashboard/summary", response_model=DashboardResponse)
def get_dashboard_summary(user_id: int, db: Session = Depends(get_db)):
    # --- 1. 餘額最高 Top 3 ---
    highest_balance = db.query(Account)\
        .filter(Account.user_id == user_id)\
        .order_by(desc(Account.current_balance))\
        .limit(3).all()

    # --- 2. 最近變動 Top 3 ---
    # 修正：使用 order_by 而非 order_id
    recently_updated = db.query(Account)\
        .filter(Account.user_id == user_id)\
        .order_by(desc(Account.updated_at))\
        .limit(3).all()

    # --- 3. 最常使用 Top 3 (精確邏輯) ---
    # 步驟 A: 建立一個聯合查詢，把所有出現過的 account_id 集合起來
    # 包含：收支紀錄、轉帳轉出、轉帳轉入
    adds_ids = db.query(AddRecord.account_id.label("aid")).filter(AddRecord.user_id == user_id)
    trans_from_ids = db.query(Transaction.from_account_id.label("aid")).filter(Transaction.user_id == user_id)
    trans_to_ids = db.query(Transaction.to_account_id.label("aid")).filter(Transaction.user_id == user_id)
    
    all_usage = adds_ids.union_all(trans_from_ids).union_all(trans_to_ids).subquery()
    
    # 步驟 B: 根據這個聯合表進行計數 (Count)
    usage_counts = db.query(
        all_usage.c.aid.label("account_id"),
        func.count(all_usage.c.aid).label("cnt")
    ).group_by(all_usage.c.aid).subquery()

    # 步驟 C: Join 回 Account 表取得完整資訊
    most_frequent_data = db.query(Account, usage_counts.c.cnt)\
        .join(usage_counts, Account.account_id == usage_counts.c.account_id)\
        .filter(Account.user_id == user_id)\
        .order_by(desc(usage_counts.c.cnt))\
        .limit(3).all()

    # 將結果轉換為 AccountBrief 格式
    most_frequent_list = []
    for acc, count in most_frequent_data:
        brief = AccountBrief.from_orm(acc)
        brief.usage_count = count
        most_frequent_list.append(brief)

    return {
        "highest_balance": highest_balance,
        "recently_updated": recently_updated,
        "most_frequent": most_frequent_list
    }