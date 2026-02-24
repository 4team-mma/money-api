from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import AddRecord, Account, Member, Notification
from web_app.models.models import Budget, SavingsGoal
from ..schemas.add import (
    AddRecordCreate,
    AddRecordResponse,
    AddRecordUpdate,
    MonthlyRecordResponse,
)
from ..dependencies import get_current_user
from typing import Optional
from sqlalchemy import func, or_, select, and_, extract
from decimal import Decimal
from datetime import date, timedelta, datetime
from web_app.services.game_service import GameService
import math  #  用於計算總頁數

router = APIRouter()


# 1. 讀取紀錄 API (支援分頁與搜尋)
@router.get("/")
async def get_records(
    page: int = 1,  # 預設第 1 頁
    page_size: int = 10,  # 每頁 10 筆
    search: Optional[str] = None,  # 搜尋關鍵字
    year: Optional[int] = None,  # 新增年份篩選
    month: Optional[int] = None,  # 新增月份篩選
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    # 建立基礎查詢
    query = db.query(AddRecord).filter(AddRecord.user_id == current_user.user_id)

    # 搜尋邏輯：如果前端有傳搜尋字串，就對 備註、類別、成員 進行模糊比對
    if search:
        query = query.filter(
            or_(
                AddRecord.add_note.ilike(f"%{search}%"),
                AddRecord.add_class.ilike(f"%{search}%"),
                AddRecord.add_member.ilike(f"%{search}%"),
            )
        )
    # 時間篩選邏輯 (與 transfers.py 一致)
    if year:
        query = query.filter(extract("year", AddRecord.add_date) == year)
    if month:
        query = query.filter(extract("month", AddRecord.add_date) == month)
    #  計算總筆數
    total_count = query.count()

    #  執行分頁
    records = (
        query.order_by(AddRecord.add_date.desc(), AddRecord.add_id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
        .all()
    )

    #  計算總頁數
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

    # 返回符合 Vue 前端 fetchTransactions 需求的格式
    return {
        "success": True,
        "data": records,
        "pagination": {
        "current_page": page,
        "page_size": page_size,
        "total_rows": total_count,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
        },
    }


@router.get(
    "/calendar/monthly",
    summary="取得月度收支清單",
    description="""
根據指定的 **年份** 與 **月份**，查詢該使用者在該月的所有收支紀錄。
- **計算功能**：自動加總該月總收入、總支出與餘額。
- **資料排序**：預設按日期降序 (Newest First)。
- **關聯查詢**：自動關聯帳戶資訊 (如貨幣、帳戶名稱)。
    """,
    response_model=MonthlyRecordResponse,  # 指定回應模型(使用 Pydantic 自動轉換)
    response_description="回傳月度統計數據與詳細紀錄清單",
)
async def get_monthly_records(
    # 讓前端傳遞年份與月份，預設為空則由後端邏輯處理或回傳錯誤
    year: int = Query(..., ge=2000, le=2100, description="年份"),
    month: int = Query(..., ge=1, le=12, description="月份"),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """
    ### 權限要求
    - 需通過 JWT Token 驗證。
    - 僅能查詢該 `user_id` 所屬的資料。

    ### 回傳格式說明 (Success JSON)
    - `total_count`: 該月總筆數
    - `monthly_income`: 總收入
    - `monthly_expenses`: 總支出
    - `monthly_balance`: 結餘 (收入 - 支出)
    - `data`: 包含 `account_name` 與 `currency` 的詳細收支紀錄清單
    """
    # 使用 SQLAlchemy ORM 與資料庫溝通
    # 1. 建立基礎查詢與 LEFT JOIN
    stmt = (
        select(
            AddRecord,
            Account.account_name,
            Account.currency,
        )
        .join(
            Account,
            and_(
                AddRecord.user_id == Account.user_id,
                AddRecord.account_id == Account.account_id,
            ),
            isouter=True,  # 實現 LEFT JOIN
        )
        .filter(AddRecord.user_id == current_user.user_id)
        # 2. 關鍵：使用 extract 函數篩選特定年、月
        .filter(extract("year", AddRecord.add_date) == year)
        .filter(extract("month", AddRecord.add_date) == month)
        # 3. 排序：按日期降序排列
        .order_by(AddRecord.add_date.desc(), AddRecord.add_id.desc())
    )

    # 執行查詢，獲取所有結果行
    results = db.execute(stmt).all()

    # 4. 資料格式化
    formatted_data = []
    monthly_income = Decimal("0.0")  # 順便計算該月總收入
    monthly_expenses = Decimal("0.0")  # 順便計算該月總支出

    for row in results:
        record = row[0]  # AddRecord ORM 物件
        account_name = row[1]  # account_name 字串
        currency = row[2]  # currency 字串

        item = {
            "add_id": record.add_id,
            "add_date": record.add_date,
            "add_amount": record.add_amount,
            "add_type": record.add_type,  # True 為收入, False 為支出
            "add_class": record.add_class,
            "add_class_icon": record.add_class_icon,
            "account_id": record.account_id,
            "add_member": record.add_member,
            "add_tag": record.add_tag,
            "add_note": record.add_note,
            "created_at": record.created_at,
            "currency": currency or "N/A",
            "account_name": account_name or "未分類帳戶",
        }
        formatted_data.append(item)

        # 累計總收入與總支出
        if record.add_type is True:  # 收入
            monthly_income += record.add_amount
        else:  # 支出
            monthly_expenses += record.add_amount

    monthly_balance = monthly_income - monthly_expenses  # 計算月結餘

    # 5. 返回結果
    return {
        "success": True,
        "year": year,
        "month": month,
        "total_count": len(formatted_data),  # 總筆數
        "monthly_income": round(monthly_income, 2),  # 四捨五入到小數兩位
        "monthly_expenses": round(monthly_expenses, 2),
        "monthly_balance": round(monthly_balance, 2),
        "data": formatted_data,
    }


@router.get("/stats/monthly")
async def get_monthly_stats(
    db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)
):
    today = date.today()
    # 本月第一天
    this_month_first = today.replace(day=1)

    # --- 獲取上個月日期範圍 ---
    # 邏輯：本月第一天減去 1 天就是上個月最後一天
    last_month_end = this_month_first - timedelta(days=1)
    last_month_first = last_month_end.replace(day=1)

    # 1. 查詢本月資料 (你原有的邏輯)
    this_expense = db.query(func.sum(AddRecord.add_amount)).filter(
        AddRecord.user_id == current_user.user_id,
        AddRecord.add_type == False,
        AddRecord.add_date >= this_month_first,
    ).scalar() or Decimal("0")
    this_income = db.query(func.sum(AddRecord.add_amount)).filter(
        AddRecord.user_id == current_user.user_id,
        AddRecord.add_type == True,
        AddRecord.add_date >= this_month_first,
    ).scalar() or Decimal("0")

    # 2. 查詢上月資料 (新增)
    last_expense = db.query(func.sum(AddRecord.add_amount)).filter(
        AddRecord.user_id == current_user.user_id,
        AddRecord.add_type == False,
        AddRecord.add_date >= last_month_first,
        AddRecord.add_date <= last_month_end,
    ).scalar() or Decimal("0")
    last_income = db.query(func.sum(AddRecord.add_amount)).filter(
        AddRecord.user_id == current_user.user_id,
        AddRecord.add_type == True,
        AddRecord.add_date >= last_month_first,
        AddRecord.add_date <= last_month_end,
    ).scalar() or Decimal("0")

    # 3. 計算成長率公式: ((本月 - 上月) / 上月) * 100
    def calc_change(this_val, last_val):
        if last_val == 0:
            return 100.0 if this_val > 0 else 0.0
        return round(float((this_val - last_val) / last_val * 100), 1)

    return {
        "month": today.strftime("%Y-%m"),
        "total_expense": float(this_expense),
        "total_income": float(this_income),
        "net_savings": float(this_income - this_expense),
        # 新增回傳欄位給前端 % 使用
        "expense_change": calc_change(this_expense, last_expense),
        "income_change": calc_change(this_income, last_income),
    }


# 3. 新增收支紀錄 API
@router.post("/", response_model=AddRecordResponse)
async def create_record(
    data: AddRecordCreate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    amt_decimal = Decimal(str(data.add_amount))
    new_record = AddRecord(user_id=current_user.user_id, **data.dict())
    db.add(new_record)

    account = db.query(Account).filter(Account.account_id == data.account_id).first()
    if account is None:
        raise HTTPException(status_code=404, detail="找不到指定帳戶")

    if data.add_type is False:  # 支出
        account.current_balance -=  amt_decimal
        
        # 預算檢查邏輯
        today = date.today()
        first_day_of_month = today.replace(day=1)

        # 判斷：只有當新增的是「本月」的紀錄時才檢查預算
        if data.add_date >= first_day_of_month:
            budget = db.query(Budget).filter(
                Budget.user_id == current_user.user_id,
                Budget.category == data.add_class
            ).first()

            if budget and budget.amount > 0:
                # 計算本月該分類總支出
                total_spent = db.query(func.sum(AddRecord.add_amount)).filter(
                    AddRecord.user_id == current_user.user_id,
                    AddRecord.add_class == data.add_class,
                    AddRecord.add_type == False,
                    AddRecord.add_date >= first_day_of_month
                ).scalar() or Decimal(0)
                
                # 加上本次新增金額 (因為 db 尚未 commit，需手動加上)
                total_spent += amt_decimal
                usage_percent = (total_spent / budget.amount) * 100

                if usage_percent >= 90:
                    # 檢查今日是否已對該分類發過預算通知
                    existing_note = db.query(Notification).filter(
                        Notification.user_id == current_user.user_id,
                        Notification.category == "budget",
                        Notification.reminder_title.like(f"%{data.add_class}%"),
                        func.date(Notification.created_at) == today
                    ).first()

                    if not existing_note:
                        new_notification = Notification(
                            user_id=current_user.user_id,
                            reminder_title=f"⚠️ 預算警報：{data.add_class} 已達 {usage_percent:.0f}%",
                            category="budget",
                            description=f"您在「{data.add_class}」的支出已達 {total_spent:,.0f} 元，接近預算上限 {budget.amount:,.0f} 元。",
                            reminder_date_start=today,
                            reminder_time=datetime.now().time(),
                            is_active=True,
                            is_read=False
                        )
                        db.add(new_notification)
            elif budget and budget.amount == 0:
                # 如果預算為 0 代表「禁止支出」，則任何一筆支出都發警告
                if amt_decimal > 0:
                    # 檢查今天是否已發過「禁止支出」警告
                    new_notification = Notification(
                        user_id=current_user.user_id,
                        reminder_title=f"🚫 超額警報：{data.add_class} 已超出預算",
                        category="budget",
                        description=f"您在「{data.add_class}」並未編列預算，但已有支出 {amt_decimal:,.0f} 元。",
                        reminder_date_start=date.today(),
                        reminder_time=datetime.now().time(),
                        is_active=True,
                        is_read=False
                    )
                    db.add(new_notification)
    else:  # 收入
        account.current_balance += amt_decimal

        # 尋找與此帳戶關聯且進行中的儲蓄目標
        goal = db.query(SavingsGoal).filter(
            SavingsGoal.account_id == data.account_id,
            SavingsGoal.user_id == current_user.user_id,
            SavingsGoal.status == "active"
        ).first()

        if goal:
            # 更新目標目前的金額
            goal.current_amount += amt_decimal
            
            # 檢查是否達標
            if goal.current_amount >= goal.target_amount:
                # 檢查是否已發過「達成通知」(避免重複發送)
                existing_note = db.query(Notification).filter(
                    Notification.user_id == current_user.user_id,
                    Notification.category == "savings",
                    Notification.reminder_title.like(f"%{goal.goal_name}%")
                ).first()

                if not existing_note:
                    # 建立賀報通知
                    new_notification = Notification(
                        user_id=current_user.user_id,
                        reminder_title=f"🎉 恭喜！儲蓄目標「{goal.goal_name}」已達成！",
                        category="savings",
                        description=f"太棒了！您已成功存下 {goal.current_amount:,.0f} 元，完成了「{goal.goal_name}」的目標。繼續保持優良的理財習慣！",
                        reminder_date_start=date.today(),
                        reminder_time=datetime.now().time(),
                        is_active=True,
                        is_read=False
                    )
                    db.add(new_notification)
                    # 同時將目標狀態改為已完成
                    goal.status = "completed"
    
    db.commit()
    db.refresh(new_record)

    # 🌟 這裡加入全域掃描器
    # 根據 add_type 判斷類別 (True: 收入, False: 支出)
    category_label = '記帳' 
    GameService.update_mission_progress(
        db, 
        user_id=current_user.user_id, 
        category=category_label,
        amount=float(new_record.add_amount), # 傳入金額供「大額支出」判定
        tag=new_record.add_tag,         # 🌟 傳入標籤內容
        record_class=new_record.add_class, # 🌟 傳入消費類別
        note=new_record.add_note,       # 🌟 傳入備註字串
        add_type=new_record.add_type    # 🌟 傳入布林值 (True=收入, False=支出)
    )
    
    return new_record


# 4. 修改紀錄 API (PATCH)
@router.patch("/{record_id}", response_model=AddRecordResponse)
async def update_record(
    record_id: int,
    data: AddRecordUpdate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    db_record = (
        db.query(AddRecord)
        .filter(
            AddRecord.add_id == record_id, AddRecord.user_id == current_user.user_id
        )
        .first()
    )
    if not db_record:
        raise HTTPException(status_code=404, detail="找不到該筆紀錄")

    # 1. 還原舊影響
    old_account = (
        db.query(Account).filter(Account.account_id == db_record.account_id).first()
    )
    if old_account:
        if db_record.add_type is False:
            old_account.current_balance += db_record.add_amount
        else:
            old_account.current_balance -= db_record.add_amount

    # 2. 更新資料
    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_record, key, value)

    db_record.add_amount = Decimal(str(db_record.add_amount))

    # 3. 套用新影響
    new_account = (
        db.query(Account).filter(Account.account_id == db_record.account_id).first()
    )
    if not new_account:
        db.rollback()
        raise HTTPException(status_code=404, detail="目標帳戶不存在")

    if db_record.add_type is False:
        new_account.current_balance -= db_record.add_amount

        # 預算檢查邏輯 (修改後若為支出則觸發)
        today = date.today()
        first_day_of_this_month = today.replace(day=1)
        
        # 只有當紀錄日期落在「本月」時才檢查預算
        if db_record.add_date >= first_day_of_this_month:
            budget = db.query(Budget).filter(
                Budget.user_id == current_user.user_id,
                Budget.category == db_record.add_class
            ).first()

            if budget and budget.amount > 0:
                # 計算本月總支出 (確保只抓本月的 adds 表紀錄)
                total_spent = db.query(func.sum(AddRecord.add_amount)).filter(
                    AddRecord.user_id == current_user.user_id,
                    AddRecord.add_class == db_record.add_class,
                    AddRecord.add_type == False,
                    AddRecord.add_date >= first_day_of_this_month
                ).scalar() or Decimal(0)

                usage_percent = (total_spent / budget.amount) * 100

                if usage_percent >= 90:
                    # 檢查今日是否已發過通知 (避免重複)
                    existing_note = db.query(Notification).filter(
                        Notification.user_id == current_user.user_id,
                        Notification.category == "budget",
                        Notification.reminder_title.like(f"%{db_record.add_class}%"),
                        func.date(Notification.created_at) == date.today()
                    ).first()

                    if not existing_note:
                        new_notification = Notification(
                            user_id=current_user.user_id,
                            reminder_title=f"⚠️ 預算警報：{db_record.add_class} 已達 {usage_percent:.0f}%",
                            category="budget",
                            description=f"修改紀錄後，您本月在「{db_record.add_class}」的支出已達 {total_spent:,.0f} 元，接近預算上限 {budget.amount:,.0f} 元。",
                            reminder_date_start=date.today(),
                            reminder_time=datetime.now().time(),
                            is_active=True,
                            is_read=False
                        )
                        db.add(new_notification)
            elif budget and budget.amount == 0:
                # 如果預算為 0 代表「禁止支出」，則任何一筆支出都發警告
                if db_record.add_amount > 0:
                    # 檢查今天是否已發過「禁止支出」警告
                    new_notification = Notification(
                        user_id=current_user.user_id,
                        reminder_title=f"🚫 超額警報：{data.add_class} 已超出預算",
                        category="budget",
                        description=f"您在「{data.add_class}」並未編列預算，但已有支出 {db_record.add_amount:,.0f} 元。",
                        reminder_date_start=date.today(),
                        reminder_time=datetime.now().time(),
                        is_active=True,
                        is_read=False
                    )
                    db.add(new_notification)
    else:
        new_account.current_balance += db_record.add_amount

        # 尋找與此帳戶關聯且進行中的儲蓄目標
        goal = db.query(SavingsGoal).filter(
            SavingsGoal.account_id == data.account_id,
            SavingsGoal.user_id == current_user.user_id,
            SavingsGoal.status == "active"
        ).first()

        if goal:
            # 更新目標目前的金額
            goal.current_amount += db_record.add_amount
            
            # 檢查是否達標
            if goal.current_amount >= goal.target_amount:
                # 檢查是否已發過「達成通知」(避免重複發送)
                existing_note = db.query(Notification).filter(
                    Notification.user_id == current_user.user_id,
                    Notification.category == "savings",
                    Notification.reminder_title.like(f"%{goal.goal_name}%")
                ).first()

                if not existing_note:
                    # 建立賀報通知
                    new_notification = Notification(
                        user_id=current_user.user_id,
                        reminder_title=f"🎉 恭喜！儲蓄目標「{goal.goal_name}」已達成！",
                        category="savings",
                        description=f"太棒了！您已成功存下 {goal.current_amount:,.0f} 元，完成了「{goal.goal_name}」的目標。繼續保持優良的理財習慣！",
                        reminder_date_start=date.today(),
                        reminder_time=datetime.now().time(),
                        is_active=True,
                        is_read=False
                    )
                    db.add(new_notification)
                    # 同時將目標狀態改為已完成
                    goal.status = "completed"

    db.commit()
    db.refresh(db_record)
    # 🌟 這裡加入全域掃描器：觸發「除錯大師」
    # 只要成功執行 Patch 請求，就視為完成一次除錯
    GameService.update_mission_progress(
        db, 
        user_id=current_user.user_id, 
        category='記帳', # 因為除錯大師的 category 是記帳
        increment=1
    )
    
    
    return db_record


# 5. 刪除紀錄 API
@router.delete("/{record_id}")
async def delete_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    record = (
        db.query(AddRecord)
        .filter(
            AddRecord.add_id == record_id, AddRecord.user_id == current_user.user_id
        )
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="紀錄不存在或無權限刪除")

    account = db.query(Account).filter(Account.account_id == record.account_id).first()
    if account:
        if record.add_type is False:
            account.current_balance += record.add_amount
        else:
            account.current_balance -= record.add_amount

            # 儲蓄目標同步還原
            # 只有刪除「收入」時，才需要扣除對應儲蓄目標的進度
            goal = db.query(SavingsGoal).filter(
                SavingsGoal.account_id == record.account_id,
                SavingsGoal.user_id == current_user.user_id
            ).first()

            if goal:
                # 扣除進度
                goal.current_amount -= record.add_amount
                
                # 狀態判定：如果扣除後低於目標，且原本狀態是已完成 (completed)
                if goal.current_amount < goal.target_amount and goal.status == "completed":
                    goal.status = "active"  # 改回進行中
                    

    db.delete(record)
    db.commit()
    return {"msg": "紀錄已成功刪除，帳戶餘額已同步更新"}
