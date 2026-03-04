import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, text
from sqlalchemy.orm import Session

from web_app.services.game_service import GameService

from ..database import get_db
from ..dependencies import admin_required, get_current_user
from ..models import (Account, AchCard, AddRecord, AIConfig, Budget, Checkin,
                      DailyMission, Feedback, LoginActivity, Member,
                      Notification, PasswordReset, SavingsGoal, Setting,
                      Transaction)
from ..utils.password import get_password_hash

router = APIRouter(dependencies=[Depends(admin_required)])


@router.get("/users")
async def get_all_users(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    return db.query(Member).offset(skip).limit(limit).all()

@router.get("/users/{user_id}", summary="🔍 取得用戶完整詳情")
async def get_admin_user_detail(user_id: int, db: Session = Depends(get_db)):
    user = db.query(Member).filter(Member.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到該會員")
    
    # 回傳資料表定義的所有欄位
    return {
        "uid": user.user_id,
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "job": user.job,
        "xp": user.xp,
        "level": user.level,
        "points": user.points,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else "從未登入"
    }

@router.post("/users/test-account", summary="🧪 建立測試帳號")
async def create_test_user(
    username: str, 
    email: str, 
    password: str, 
    db: Session = Depends(get_db)
):
    # 1. 檢查 Email 是否已存在
    if db.query(Member).filter(Member.email == email).first():
        raise HTTPException(status_code=400, detail="Email 已被註冊")
    
    # 2. 建立新成員
    new_user = Member(
        username=username,
        email=email,
        name=f"測試員-{username}",
        password=get_password_hash(password), # 務必加密
        role="test",
        status="active",
        job="系統測試員",
        xp=0,     # 給予初始經驗值
        level=1,
        points=100  # 給予初始點數
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"msg": f"測試帳號 {username} 建立成功", "user_id": new_user.user_id}

@router.post("/admins", summary="🛡️ 建立新管理員")
async def create_admin_user(
    username: str, 
    email: str, 
    password: str, 
    name: str,
    db: Session = Depends(get_db)
):
    # 檢查重複
    if db.query(Member).filter((Member.email == email) | (Member.username == username)).first():
        raise HTTPException(status_code=400, detail="帳號或 Email 已存在")
    
    new_admin = Member(
        username=username,
        email=email,
        name=name,
        password=get_password_hash(password),
        role="admin",  # 🚀 關鍵：權限設為管理員
        status="active",
        job="系統管理員"
    )
    
    db.add(new_admin)
    db.commit()
    return {"msg": f"管理員 {username} 建立成功"}

@router.post("/users/test-accounts/reset", summary="♻️ 一鍵重置所有測試帳號數據")
async def reset_all_test_users(db: Session = Depends(get_db)):
    # 找出所有測試員的 ID
    test_user_ids = [u.user_id for u in db.query(Member.user_id).filter(Member.role == "test").all()]
    
    if not test_user_ids:
        return {"msg": "目前沒有測試帳號需要重置"}

    # 🌟 關鍵修正：必須先刪除「依賴帳戶 ID」的資料
    # 1. 先刪除轉帳紀錄（它依賴 account_id）
    db.query(Transaction).filter(Transaction.user_id.in_(test_user_ids)).delete(synchronize_session=False)
    
    # 2. 刪除收支紀錄（它也依賴 account_id）
    db.query(AddRecord).filter(AddRecord.user_id.in_(test_user_ids)).delete(synchronize_session=False)
    
    # 3. 刪除儲蓄目標（這也有外鍵連到 Account）
    db.query(SavingsGoal).filter(SavingsGoal.user_id.in_(test_user_ids)).delete(synchronize_session=False)

    # 4. 🌟 最後才刪除帳戶本體 (這時已經沒有其他表連著它了，就不會報錯)
    db.query(Account).filter(Account.user_id.in_(test_user_ids)).delete(synchronize_session=False)

    # 5. 清理遊戲化數據
    db.query(DailyMission).filter(DailyMission.user_id.in_(test_user_ids)).delete(synchronize_session=False)
    db.query(AchCard).filter(AchCard.user_id.in_(test_user_ids)).delete(synchronize_session=False)
    db.query(Checkin).filter(Checkin.user_id.in_(test_user_ids)).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.user_id.in_(test_user_ids)).delete(synchronize_session=False)

    # 6. 重置數值
    db.query(Member).filter(Member.user_id.in_(test_user_ids)).update({
        "xp": 0, "level": 1, "points": 0, "status": "active"
    }, synchronize_session=False)

    db.commit()
    return {"msg": f"已成功重置 {len(test_user_ids)} 個測試帳號的數據"}

@router.post("/users/test-accounts/generate-data", summary="🎲 注入完整模擬數據")
async def generate_test_data(db: Session = Depends(get_db)):
    # 1. 篩選出所有系統測試員
    test_users = db.query(Member).filter(Member.job == "系統測試員").all()
    if not test_users:
        raise HTTPException(status_code=404, detail="找不到測試帳號，請先建立")

    # 定義支出分類與對應圖示
    categories = [
        {"name": "餐飲", "icon": "🍔"},
        {"name": "交通", "icon": "🚗"},
        {"name": "購物", "icon": "🛍️"},
        {"name": "娛樂", "icon": "🎮"},
        {"name": "醫療", "icon": "🏥"},
        {"name": "學習", "icon": "📚"}
    ]

    for user in test_users:
        # 2. 檢查/建立測試帳戶 (符合 Account 模型定義)
        test_account = db.query(Account).filter(Account.user_id == user.user_id).first()
        if not test_account:
            # 1. 初始資金調高，確保不會輕易變成負數
            test_account = Account(
                user_id=user.user_id,
                account_type="bank",
                account_name="預設銀行",
                initial_balance=Decimal("50000.00"), # 提高初始金額
                current_balance=Decimal("50000.00"),
                exclude_from_assets=False,
                account_icon="💰"
            )
            db.add(test_account)
            db.flush()

        # 2. 修正：先注入一筆大額「薪資收入」，確保餘額充足
        base_income = AddRecord(
            user_id=user.user_id,
            add_date=date.today() - timedelta(days=60),
            add_amount=Decimal("80000.00"),
            add_type=True, # 收入
            add_class="薪資",
            add_class_icon="💰",
            account_id=test_account.account_id,
            add_member=user.name[:10],
            add_note="[系統生成] 初始化測試資金"
        )
        db.add(base_income)
        test_account.current_balance += Decimal("80000.00")
        db.flush() # 取得 account_id 以供後續 AddRecord 使用

        # 3. 注入 20~40 筆隨機收支 (符合 AddRecord 模型定義)
        for _ in range(random.randint(20, 40)):
            is_income = random.random() < 0.15 # 15% 機率為收入
            selected = random.choice(categories)
            amt = Decimal(str(random.randint(50, 5000)))

            new_record = AddRecord(
                user_id=user.user_id,
                add_date=date.today() - timedelta(days=random.randint(0, 60)), # 隨機過去兩個月
                add_amount=amt,
                add_type=is_income,
                add_class="薪資" if is_income else selected["name"],
                add_class_icon="💰" if is_income else selected["icon"],
                account_id=test_account.account_id,
                add_member=user.name[:10], # 限制長度符合 String(10)
                add_tag=random.choice(["需要", "想要", "固定", "其它"]),
                add_note="[系統生成] 自動化測試數據"
            )
            db.add(new_record)
            
            # 更新帳戶餘額 (模擬真實交易)
            if is_income:
                test_account.current_balance += amt
            else:
                test_account.current_balance -= amt

        # 4. 成長進度模擬
        GameService.add_user_xp(db, user, random.randint(1000, 3000))
        user.last_login = datetime.now()
        

    db.commit()
    return {"msg": f"已為 {len(test_users)} 位測試員注入隨機數據"}

@router.post("/users/{user_id}/xp", summary="✨ 手動調整用戶經驗值")
async def adjust_user_xp(user_id: int, amount: int, db: Session = Depends(get_db)):
    user = db.query(Member).filter(Member.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到會員")
    
    # 🛡️ 調用封裝好的遊戲服務邏輯
    # 它會自動處理：user.xp += amount -> 判斷升級 -> 扣除消耗 -> 重複判定直到 XP 不足升級
    GameService.add_user_xp(db, user, amount)
    
    db.commit()
    db.refresh(user)
    
    return {
        "msg": f"已為 {user.username} 調整 {amount} XP",
        "new_xp": user.xp,
        "new_level": user.level,
        "next_level_xp": GameService.get_required_xp(user.level) # 回傳下一級門檻供前端顯示
    }

@router.post("/users/{user_id}/notify", summary="🔔 發送系統通知")
async def send_user_notification(
    user_id: int, 
    title: str, 
    description: str, 
    db: Session = Depends(get_db)
):
    new_notify = Notification(
        user_id=user_id,
        reminder_title=title,
        description=description,
        category="manual",              # 手動發送
        reminder_date_start=date.today(), # 今天開始
        repeat_cycle="none",            # 不重複
        is_active=True,
        is_read=False
    )
    db.add(new_notify)
    db.commit()
    return {"msg": f"通知已成功送達用戶 {user_id} 的提醒清單"}

# 管理員強制刪除用戶
@router.delete("/users/{user_id}", summary="🗑️ 管理員強制註銷帳號", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_user(
    user_id: int, 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    target_user = db.query(Member).filter(Member.user_id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="找不到該使用者")

    # 🛡️ 安全檢查：防止管理員自刪 (選配)
    if current_user.user_id == user_id:
        raise HTTPException(status_code=400, detail="不能在管理後台刪除自己")

    # 🌟 手動清除所有關聯資料 (包含新舊功能)
    # 新增的遊戲化與系統功能
    db.query(DailyMission).filter(DailyMission.user_id == user_id).delete()
    db.query(AchCard).filter(AchCard.user_id == user_id).delete()
    db.query(Checkin).filter(Checkin.user_id == user_id).delete()
    db.query(Setting).filter(Setting.user_id == user_id).delete()
    db.query(LoginActivity).filter(LoginActivity.user_id == user_id).delete()
    db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id).delete()
    db.query(AIConfig).filter(AIConfig.user_id == user_id).delete()
    db.query(Budget).filter(Budget.user_id == user_id).delete()

    # 原本舊有的基礎功能
    db.query(Transaction).filter(Transaction.user_id == user_id).delete()
    db.query(AddRecord).filter(AddRecord.user_id == user_id).delete()
    db.query(Account).filter(Account.user_id == user_id).delete()
    db.query(Notification).filter(Notification.user_id == user_id).delete()
    db.query(Feedback).filter(Feedback.user_id == user_id).delete()
    db.query(PasswordReset).filter(PasswordReset.user_id == user_id).delete()

    db.delete(target_user)
    db.commit()
    return None

@router.patch("/users/{user_id}/block", summary="🚫 切換用戶停用/啟用狀態")
async def toggle_user_status(user_id: int, db: Session = Depends(get_db)):
    user = db.query(Member).filter(Member.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到會員")
    # 切換邏輯：如果是 active 就變 banned，反之亦然
    new_status = "banned" if user.status == "active" else "active"
    user.status = new_status
    db.commit()
    db.refresh(user)
    
    status_text = "停用" if new_status == "banned" else "啟用"
    return {"msg": f"會員 {user.username} 已成功{status_text}", "status": new_status}

# 用戶價值分析表格數據
@router.get("/stats/rankings")
async def get_combined_admin_stats(db: Session = Depends(get_db)):
    now = datetime.now()

    # 1. 基礎排行榜 (維持原樣)
    category_ranks = db.query(AddRecord.add_class, func.sum(AddRecord.add_amount)).filter(AddRecord.add_type == False).group_by(AddRecord.add_class).order_by(func.sum(AddRecord.add_amount).desc()).limit(10).all()
    frequency_ranks = db.query(Member.username, Member.name, func.count(AddRecord.add_id)).join(AddRecord, Member.user_id == AddRecord.user_id).filter(Member.role == "user").group_by(Member.user_id).order_by(func.count(AddRecord.add_id).desc()).limit(5).all()
    savings_ranks = db.query(Member.username, Member.name, func.sum(Account.current_balance)).join(Account, Member.user_id == Account.user_id).filter(Member.role == "user").group_by(Member.user_id).order_by(func.sum(Account.current_balance).desc()).limit(5).all()
    xp_ranks = db.query(Member.username, Member.name, Member.xp, Member.level).filter(Member.role == "user").order_by(Member.xp.desc()).limit(5).all()

    # 2. 子查詢 (金額與月份)
    net_worth_sub = db.query(
        Account.user_id,
        func.sum(case((Account.exclude_from_assets == False, Account.current_balance), else_=0)).label("sum_net_worth")
    ).group_by(Account.user_id).subquery()

    finance_sub = db.query(
        AddRecord.user_id,
        func.sum(case((AddRecord.add_type == True, AddRecord.add_amount), else_=0)).label("sum_income"),
        func.sum(case((AddRecord.add_type == False, AddRecord.add_amount), else_=0)).label("sum_spent"),
        func.count(func.distinct(func.date_format(func.coalesce(AddRecord.add_date, func.current_date()), '%Y-%m'))).label("active_months_count"),
        func.count(func.distinct(AddRecord.add_date)).label("accounting_days")
    ).group_by(AddRecord.user_id).subquery()

    # 3. 操作活躍度天數 (UNION 查詢)
    op_days_sql = """
        SELECT user_id, DATE(created_at) as op_date FROM adds UNION
        SELECT user_id, DATE(updated_at) as op_date FROM adds UNION
        SELECT user_id, DATE(created_at) as op_date FROM accounts UNION
        SELECT user_id, DATE(updated_at) as op_date FROM accounts UNION
        SELECT user_id, DATE(created_at) as op_date FROM transactions UNION
        SELECT user_id, DATE(updated_at) as op_date FROM transactions
    """
    op_counts = db.execute(text(f"SELECT user_id, COUNT(DISTINCT op_date) as actual_op_days FROM ({op_days_sql}) as combined_ops GROUP BY user_id")).all()
    op_map = {row[0]: row[1] for row in op_counts}

    # 4. 主查詢 (✨ 加入 Member.updated_at)
    results = db.query(
        Member.user_id,
        Member.username,
        Member.name,
        Member.created_at.label("reg_date"),
        Member.updated_at.label("last_active"),  # ✨ 加入這行
        func.coalesce(net_worth_sub.c.sum_net_worth, 0).label("net_worth"),
        func.coalesce(finance_sub.c.sum_income, 0).label("income"),
        func.coalesce(finance_sub.c.sum_spent, 0).label("spent"),
        func.coalesce(finance_sub.c.active_months_count, 1).label("m_count"),
        func.coalesce(finance_sub.c.accounting_days, 0).label("a_days")
    ).outerjoin(net_worth_sub, Member.user_id == net_worth_sub.c.user_id)\
     .outerjoin(finance_sub, Member.user_id == finance_sub.c.user_id)\
     .filter(Member.role == "user").all()

    # 5. 合併計算與狀態判斷
    user_insights = []
    for r in results:
        # A. 計算時間
        reg_days = max((now - r.reg_date).days + 1, 1) # ✨ 分母同步 MySQL (+1)
        days_since_active = (now.date() - r.last_active.date()).days

        # B. 判斷燈號狀態
        if days_since_active <= 3:
            current_status = "green"
        elif days_since_active <= 14:
            current_status = "yellow"
        else:
            current_status = "red"

        # C. 計算金額平均與比率
        denom_months = float(max(r.m_count, 1))
        avg_income = float(r.income or 0) / denom_months
        avg_spent = float(r.spent or 0) / denom_months

        coverage_rate = min(round(((r.a_days or 0) / reg_days) * 100, 1), 100.0)
        actual_op_days = op_map.get(r.user_id, 1)
        active_rate = min(round((actual_op_days / reg_days) * 100, 1), 100.0)

        user_insights.append({
            "username": r.username,
            "name": r.name,
            "status": current_status, # ✨ 使用動態判斷的燈號
            "financials": {
                "net_worth": int(r.net_worth or 0),
                "monthly_income": int(avg_income),
                "monthly_spent": int(avg_spent)
            },
            "engagement": {
                "active_rate": active_rate,
                "coverage_rate": coverage_rate
            }
        })

    return {
        "category_spending": [{"name": r[0], "value": float(r[1])} for r in category_ranks],
        "active_bees": [{"name": r[1], "value": r[2]} for r in frequency_ranks],
        "wealth_masters": [{"name": r[1], "value": float(r[2])} for r in savings_ranks],
        "xp_immortals": [{"name": r[1], "level": r[3], "value": r[2]} for r in xp_ranks],
        "user_insights": user_insights
    }

# 收/支類別統計
@router.get("/stats/category-analysis")
async def get_category_analysis(type: int = 0, db: Session = Depends(get_db)):
    # type=0 是支出 (預設), type=1 是收入

    # 1. 取得全局分母 (根據 type 切換)
    total_amount = db.query(func.sum(AddRecord.add_amount)).filter(AddRecord.add_type == type, AddRecord.add_amount != None).scalar() or 1
    total_count = db.query(func.count(AddRecord.add_id)).filter(AddRecord.add_type == type, AddRecord.add_amount != None).scalar() or 1
    total_users_count = db.query(func.count(Member.user_id)).filter(Member.role == "user").scalar() or 1

    # 2. 中位數計算 (SQL 也要帶入參數)
    median_subquery = text("""
        SELECT add_class, AVG(add_amount) as median_val
        FROM (
            SELECT add_class, add_amount,
                   ROW_NUMBER() OVER (PARTITION BY add_class ORDER BY add_amount) as row_num,
                   COUNT(*) OVER (PARTITION BY add_class) as total_rows
            FROM adds
            WHERE add_type = :type AND add_amount IS NOT NULL
            ) as ranked_data
        WHERE row_num IN (FLOOR((total_rows+1)/2), CEIL((total_rows+1)/2))
        GROUP BY add_class
    """).bindparams(type=type) # ✨ 這裡傳入參數
    
    median_results = db.execute(median_subquery).all()
    median_map = {row[0]: float(row[1]) for row in median_results}

    # 3. 主查詢 (同樣帶入 type)
    category_stats = db.query(
        AddRecord.add_class,
        func.avg(AddRecord.add_amount).label("avg_amount"),
        func.sum(AddRecord.add_amount).label("sum_amount"),
        func.count(AddRecord.add_id).label("freq_count"),
        func.count(func.distinct(AddRecord.user_id)).label("user_reach")
    ).filter(
        AddRecord.add_type == type, 
        AddRecord.add_amount != None
    ).group_by(
        AddRecord.add_class
    ).all()

    # 4. 格式化回傳 (邏輯不變)
    formatted_results = []
    for i, r in enumerate(category_stats, 1):
        formatted_results.append({
            "id": i,
            "category": r.add_class,
            "avg_value": round(float(r.avg_amount or 0), 0),
            "median_value": round(float(median_map.get(r.add_class, 0)), 0),
            "amount_ratio": round((float(r.sum_amount or 0) / float(total_amount)) * 100, 1) if total_amount > 0 else 0,
            "user_coverage": round((float(r.user_reach) / float(total_users_count)) * 100, 1) if total_users_count > 0 else 0,
            "freq_ratio": round((float(r.freq_count) / float(total_count)) * 100, 1) if total_count > 0 else 0
        })

    return formatted_results

# 帳戶資產/負債分佈分析
@router.get("/stats/account-analysis")
async def get_account_analysis(db: Session = Depends(get_db)):
    # 1. 取得全局分母
    # 總用戶數 (分母：計算滲透率)
    total_users_count = db.query(func.count(Member.user_id)).filter(Member.role == "user").scalar() or 1
    
    # 所有帳戶的絕對值總額 (分母：計算配置比例，使用絕對值避免資產負債抵銷導致比例異常)
    all_accounts_sum = db.query(func.sum(func.abs(Account.current_balance))).scalar() or 1

    # 2. 中位數計算 (針對 account_type 分組)
    # 邏輯：先幫每個類型的金額排序編號，再抓取中間那幾筆取平均
    median_sql = text("""
        SELECT account_type, AVG(current_balance) as median_val
        FROM (
            SELECT account_type, current_balance,
                   ROW_NUMBER() OVER (PARTITION BY account_type ORDER BY current_balance) as row_num,
                   COUNT(*) OVER (PARTITION BY account_type) as total_rows
            FROM accounts
        ) as ranked_data
        WHERE row_num IN (FLOOR((total_rows+1)/2), CEIL((total_rows+1)/2))
        GROUP BY account_type
    """)
    median_results = db.execute(median_sql).all()
    median_map = {row[0]: float(row[1]) for row in median_results}

    # 3. 主查詢：聚合計算
    # 統計各類型的：總額、帳戶筆數、不重複使用者數
    account_stats = db.query(
        Account.account_type,
        func.sum(Account.current_balance).label("sum_amount"),
        func.count(Account.account_id).label("acc_count"),
        func.count(func.distinct(Account.user_id)).label("user_reach")
    ).group_by(Account.account_type).all()

    # 4. 格式化回傳
    # 這裡對應妳前端要求的欄位
    analysis_results = []
    for i, r in enumerate(account_stats, 1):
        owner_count = float(r.user_reach or 0)
        
        analysis_results.append({
            "id": i,
            "account_type": r.account_type,
            "total_amount": float(r.sum_amount or 0),
            # 配置比例 (該類別絕對值 / 全域絕對值總額)
            "allocation_ratio": round((abs(float(r.sum_amount or 0)) / float(all_accounts_sum)) * 100, 1),
            # 滲透率 (有多少比例的用戶開立此帳戶)
            "penetration_rate": round((owner_count / float(total_users_count)) * 100, 1),
            # 平均帳戶數 (有開的人平均開幾個)
            "avg_count_per_user": round(float(r.acc_count) / owner_count, 1) if owner_count > 0 else 0,
            # 帳戶平均總額 (該類別總額 / 擁有者人數)
            "avg_amount_per_user": round(float(r.sum_amount or 0) / owner_count, 0) if owner_count > 0 else 0,
            # 中位數
            "median_amount": round(median_map.get(r.account_type, 0), 0)
        })

    # 按照總額大小排序回傳
    return sorted(analysis_results, key=lambda x: abs(x['total_amount']), reverse=True)



# 最上面小卡

@router.get("/stats/dashboard-summary")
async def get_dashboard_summary(db: Session = Depends(get_db)):
    now = datetime.now()

    # 1. 總註冊用戶數 (排除管理員)
    total_users_query = db.query(Member).filter(Member.role == "user").all()
    total_users_count = len(total_users_query)
    
    # 2. 活躍用戶數 (最近 7 天內有更新紀錄)
    seven_days_ago = now - timedelta(days=7)
    active_users_count = db.query(func.count(Member.user_id)).filter(
        Member.role == "user",
        Member.updated_at >= seven_days_ago
    ).scalar() or 0

    # 3. 收/支總筆數
    total_transactions = db.query(func.count(AddRecord.add_id)).filter(
        AddRecord.add_amount != None
    ).scalar() or 0

    # 4. 準備計算平均活躍度 (需要 UNION 查詢)
    op_days_sql = """
        SELECT user_id, DATE(created_at) as op_date FROM adds UNION
        SELECT user_id, DATE(updated_at) as op_date FROM adds UNION
        SELECT user_id, DATE(created_at) as op_date FROM accounts UNION
        SELECT user_id, DATE(updated_at) as op_date FROM accounts UNION
        SELECT user_id, DATE(created_at) as op_date FROM transactions UNION
        SELECT user_id, DATE(updated_at) as op_date FROM transactions
    """
    op_counts = db.execute(text(f"SELECT user_id, COUNT(DISTINCT op_date) as actual_op_days FROM ({op_days_sql}) as combined_ops GROUP BY user_id")).all()
    op_map = {row[0]: row[1] for row in op_counts}

    # 5. 計算平均值
    total_active_rate = 0
    total_coverage_rate = 0

    if total_users_count > 0:
        for u in total_users_query:
            # 這裡要抓該用戶的記帳天數
            a_days = db.query(func.count(func.distinct(AddRecord.add_date))).filter(AddRecord.user_id == u.user_id).scalar() or 0
            reg_days = max((now - u.created_at).days + 1, 1)
            
            # 覆蓋率
            total_coverage_rate += min(((a_days / reg_days) * 100), 100.0)
            # 活躍度
            actual_op_days = op_map.get(u.user_id, 0)
            total_active_rate += min(((actual_op_days / reg_days) * 100), 100.0)

        avg_coverage = total_coverage_rate / total_users_count
        avg_activity = total_active_rate / total_users_count
    else:
        avg_coverage = 0
        avg_activity = 0

    return {
        "total_users": total_users_count,
        "active_users": active_users_count,
        "total_transactions": f"{total_transactions:,}",
        "avg_activity": f"{avg_activity:.1f}%",
        "avg_coverage": f"{avg_coverage:.1f}%"
    }