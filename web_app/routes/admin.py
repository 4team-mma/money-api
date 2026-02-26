from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db
from ..models import (
    Member,
    AddRecord,
    Account,
    Transaction,
    Notification,
    Feedback,
    PasswordReset,
    DailyMission,
    AchCard,
    Checkin,
    Setting,
    LoginActivity,
    SavingsGoal,
    AIConfig,
    Budget
)
from ..dependencies import admin_required, get_current_user
from web_app.services.game_service import GameService
from datetime import date, timedelta, datetime
from ..utils.password import get_password_hash
import random
from decimal import Decimal

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
            test_account = Account(
                user_id=user.user_id,
                account_type="現金",
                account_name="測試模擬錢包",
                currency="NT$",
                initial_balance=Decimal("10000.00"),
                current_balance=Decimal("10000.00"),
                account_icon="👛",
                exclude_from_assets=False
            )
            db.add(test_account)
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

@router.get("/stats/rankings")
async def get_admin_rankings(db: Session = Depends(get_db)):
    # 1. 💰 各路財神消費榜 (修正處：補上 .all() 括號)
    category_ranks = (
        db.query(
            AddRecord.add_class, func.sum(AddRecord.add_amount).label("total_amount")
        )
        .filter(AddRecord.add_type == False)
        .group_by(AddRecord.add_class)
        .order_by(func.sum(AddRecord.add_amount).desc())
        .limit(10)
        .all()
    )  # ✅ 這裡補上了 ()

    # 2. ✍️ 勤勞小蜜蜂獎
    frequency_ranks = (
        db.query(
            Member.username, Member.name, func.count(AddRecord.add_id).label("count")
        )
        .join(AddRecord, Member.user_id == AddRecord.user_id)
        .filter(Member.role == "user")
        .group_by(Member.user_id)
        .order_by(func.count(AddRecord.add_id).desc())
        .limit(5)
        .all()
    )

    # 3. 🛡️ 金庫大總管
    savings_ranks = (
        db.query(
            Member.username,
            Member.name,
            func.sum(Account.current_balance).label("total_balance"),
        )
        .join(Account, Member.user_id == Account.user_id)
        .filter(Member.role == "user")
        .group_by(Member.user_id)
        .order_by(func.sum(Account.current_balance).desc())
        .limit(5)
        .all()
    )

    # 4. 🆙 修仙進度表
    xp_ranks = (
        db.query(Member.username, Member.name, Member.xp, Member.level)
        .filter(Member.role == "user")
        .order_by(Member.xp.desc())
        .limit(5)
        .all()
    )

    # 5. 🏆 財富英雄榜
    top_spenders = (
        db.query(
            Member.username,
            Member.name,
            func.sum(AddRecord.add_amount).label("total_spent"),
            func.count(AddRecord.add_id).label("tx_count"),
        )
        .join(AddRecord, Member.user_id == AddRecord.user_id)
        .filter(Member.role == "user", AddRecord.add_type == False)
        .group_by(Member.user_id)
        .order_by(func.sum(AddRecord.add_amount).desc())
        .limit(10)
        .all()
    )

    # 格式化回傳 (加入空值檢查 or 0)
    return {
        "category_spending": [
            {"name": r.add_class, "value": float(r.total_amount or 0)}
            for r in category_ranks
        ],
        "active_bees": [
            {"username": r.username, "name": r.name, "value": r.count, "role": "user"}
            for r in frequency_ranks
        ],
        "wealth_masters": [
            {
                "username": r.username,
                "name": r.name,
                "value": float(r.total_balance or 0),
                "role": "user",
            }
            for r in savings_ranks
        ],
        "xp_immortals": [
            {
                "username": r.username,
                "name": r.name,
                "value": r.xp,
                "level": r.level,
                "role": "user",
            }
            for r in xp_ranks
        ],
        "top_spenders": [
            {
                "username": r.username,
                "name": r.name,
                "totalSpent": float(r.total_spent or 0),
                "transactions": r.tx_count,
                #  修正除以零的判斷邏輯
                "avgSpent": (
                    float(r.total_spent or 0) / r.tx_count
                    if (r.tx_count and r.tx_count > 0)
                    else 0
                ),
                "role": "user",
            }
            for r in top_spenders
        ],
    }
