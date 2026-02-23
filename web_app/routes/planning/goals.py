from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import and_
from web_app.schemas.goal import SavingsUpdate
from web_app.models.models import SavingsGoal, Member, Account
from web_app.dependencies import get_db, get_current_user
from decimal import Decimal
from datetime import date

router = APIRouter()

@router.get("")
def get_savings_goals(db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    goals = db.query(SavingsGoal).filter(SavingsGoal.user_id == current_user.user_id).all()
    
    for goal in goals:
        if goal.account_id:
            # 如果有指定帳戶，抓取該帳戶餘額
            target_acc = db.query(Account).filter(Account.account_id == goal.account_id).first()
            goal.current_amount = target_acc.current_balance if target_acc else Decimal("0.0")
        else:
            # 如果沒指定，預設顯示 0 或您可以定義為所有儲蓄帳戶總和
            goal.current_amount = Decimal("0.0")
            
        # 自動判定狀態
        if goal.current_amount >= goal.target_amount:
            goal.status = "completed"
    
    return goals

@router.post("/batch")
def batch_sync_savings(
    goals: list[SavingsUpdate], 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    """
    批次同步儲蓄目標：支援新增、更新、刪除與帳戶連動。
    """
    # 1. 獲取資料庫現有的目標 ID 集合 (用於比對刪除)
    db_goals = db.query(SavingsGoal).filter(
        SavingsGoal.user_id == current_user.user_id
    ).all()
    db_goal_ids = {g.goal_id for g in db_goals}
    
    # 2. 獲取前端傳入的有效 ID 集合
    incoming_ids = {g.goal_id for g in goals if g.goal_id is not None}

    # 3. 執行刪除：不在傳入清單中的舊資料 (使用者在前端點了 ✕)
    ids_to_delete = db_goal_ids - incoming_ids
    if ids_to_delete:
        db.query(SavingsGoal).filter(
            and_(
            SavingsGoal.user_id == current_user.user_id, 
            SavingsGoal.goal_id.in_(ids_to_delete)
            )
        ).delete(synchronize_session=False)

    # 4. 執行新增或更新 (UPSERT)
    for g_data in goals:
        # 確保金額初始化為 Decimal 0
        current_amt = Decimal(str(g_data.current_amount or "0.0")) 
        
        if g_data.account_id:
            acc = db.query(Account).filter(Account.account_id == g_data.account_id).first()
            if acc:
                # 確保從帳戶拿到的餘額也是有效的 Decimal
                current_amt = acc.current_balance if acc.current_balance is not None else Decimal("0.0")

        # 判定狀態
        calc_status = "active"
        if current_amt >= g_data.target_amount and g_data.target_amount > 0:
            calc_status = "completed"
        elif g_data.target_date and g_data.target_date < date.today():
            calc_status = "failed"
        else:
            calc_status = g_data.status # 預設維持前端傳來的狀態

        # 準備更新字典
        save_data = {
            "goal_name": g_data.goal_name,
            "account_id": g_data.account_id,
            "target_amount": g_data.target_amount,
            "current_amount": current_amt,
            "target_date": g_data.target_date,
            "status": calc_status
        }

        if g_data.goal_id and g_data.goal_id in db_goal_ids:
            # 更新現有目標
            db.query(SavingsGoal).filter(
            SavingsGoal.goal_id == g_data.goal_id
            ).update(save_data)
        else:
            # 新增目標
            new_goal = SavingsGoal(
            user_id=current_user.user_id,
            **save_data
            )
            db.add(new_goal)

    db.commit()
    return {"status": "success", "message": f"已同步 {len(goals)} 個儲蓄目標"}