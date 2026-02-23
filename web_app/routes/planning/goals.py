from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from web_app.schemas.goal import SavingsUpdate, SavingsGoalResponse
from web_app.models.models import SavingsGoal, Member, Account
from web_app.dependencies import get_db, get_current_user
from decimal import Decimal
from datetime import date

router = APIRouter()

@router.get(
    "",
    response_model=list[SavingsGoalResponse],
    summary="獲取目前使用者的所有儲蓄目標",
    description="從資料庫提取目前登入使用者的儲蓄計畫，並自動根據關聯帳戶的最新餘額更新進度與狀態。"
)
def get_savings_goals(
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    goals = db.query(SavingsGoal).filter(SavingsGoal.user_id == current_user.user_id).all()
    
    for goal in goals:
        if goal.account_id:
            # 如果有指定帳戶，抓取該帳戶餘額
            target_acc = db.query(Account).filter(Account.account_id == goal.account_id).first()
            goal.current_amount = target_acc.current_balance if target_acc else Decimal("0.0")
        else:
            goal.current_amount = Decimal("0.0")
            
        # 自動判定狀態
        if goal.current_amount >= goal.target_amount:
            goal.status = "completed"
    
    return goals

@router.post(
    "/batch",
    status_code=status.HTTP_200_OK,
    summary="批次同步儲蓄目標 (UPSERT & Sync)",
    description="""
### 核心功能說明：
本端點採 **全量同步 (Full Sync)** 策略，適用於前端整頁儲蓄列表的存檔動作：

1. **新增 (Create)**: 若傳入物件不含 `goal_id`，系統將視為新目標自動建立。
2. **更新 (Update)**: 若傳入物件含 `goal_id` 且存在於資料庫，將更新現有屬性（名稱、金額、截止日等）。
3. **刪除 (Delete)**: **重要！** 若資料庫現有 ID **未包含**在本次傳入清單中，系統將判定使用者已刪除該筆資料並從 DB 移除。
4. **帳戶連動 (Account Sync)**: 
    - 若傳入 `account_id`，系統將**強制忽略**傳入的 `current_amount`，改採該帳戶的最新餘額。
    - 若 `account_id` 為 `null`，則使用傳入的 `current_amount` 值。

### 自動狀態判定 (Status Logic)：
- **completed**: 當 `current_amount` >= `target_amount`。
- **failed**: 當 `target_date` 已過期且未達標。
- **active**: 進行中的目標。
    """,
    responses={
        200: {
            "description": "同步成功",
            "content": {
                "application/json": {
                    "example": {"status": "success", "message": "已同步 3 個儲蓄目標"}
                }
            }
        }
    }
)
def batch_sync_savings(
    goals: list[SavingsUpdate], 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    """
    實作邏輯：
    1. 獲取舊 ID 集合 (db_goal_ids)
    2. 計算應刪除清單 (db_goal_ids - incoming_ids)
    3. 遍歷 goals 執行新增或更新
    4. 計算狀態並回寫資料庫
    """
    # 1. 獲取資料庫現有的目標 ID 集合 (用於比對刪除)
    db_goals = db.query(SavingsGoal).filter(
        SavingsGoal.user_id == current_user.user_id
    ).all()
    db_goal_ids = {g.goal_id for g in db_goals}
    
    # 2. 獲取前端傳入的有效 ID 集合
    incoming_ids = {g.goal_id for g in goals if g.goal_id is not None}

    # 3. 執行刪除
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
        current_amt = Decimal(str(g_data.current_amount or "0.0")) 
        
        if g_data.account_id:
            acc = db.query(Account).filter(Account.account_id == g_data.account_id).first()
            if acc:
                current_amt = acc.current_balance if acc.current_balance is not None else Decimal("0.0")

        # 判定狀態
        calc_status = "active"
        if current_amt >= g_data.target_amount and g_data.target_amount > 0:
            calc_status = "completed"
        elif g_data.target_date and g_data.target_date < date.today():
            calc_status = "failed"
        else:
            calc_status = g_data.status

        save_data = {
            "goal_name": g_data.goal_name,
            "account_id": g_data.account_id,
            "target_amount": g_data.target_amount,
            "current_amount": current_amt,
            "target_date": g_data.target_date,
            "status": calc_status
        }

        if g_data.goal_id and g_data.goal_id in db_goal_ids:
            db.query(SavingsGoal).filter(
                SavingsGoal.goal_id == g_data.goal_id
            ).update(save_data)
        else:
            new_goal = SavingsGoal(
                user_id=current_user.user_id,
                **save_data
            )
            db.add(new_goal)

    db.commit()
    return {"status": "success", "message": f"成功同步 {len(goals)} 個儲蓄目標，刪除 {len(ids_to_delete)} 個"}