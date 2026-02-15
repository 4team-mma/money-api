from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, timedelta
from web_app.database import get_db
from web_app.models import Checkin, Member
from web_app.schemas.gamification import checkin as schemas
from web_app.dependencies import get_current_user
import calendar

# 簽到規則可參閱雲端excel檔的成就收集頁面

router = APIRouter()

@router.post("/action", response_model=schemas.CheckinResponse)
def perform_checkin(
    current_user: Member = Depends(get_current_user),
    db: Session = Depends(get_db)):

    uid = current_user.user_id
    today = date.today()

    # 1. 檢查今天是否已打卡
    existing = db.query(Checkin).filter(
        Checkin.user_id == uid,
        Checkin.checkin_date == today
    ).first()

    if existing:
        # 為了前端好處理，重複打卡建議噴 400 錯誤
        raise HTTPException(status_code=400, detail="今天已經打過卡囉！")

    # 2. 連續天數與循環邏輯
    yesterday = today - timedelta(days=1)
    last_record = db.query(Checkin).filter(Checkin.user_id == uid, Checkin.checkin_date == yesterday).first()

    streak_count = last_record.streak_count + 1 if last_record else 1
    cycle_day = (streak_count - 1) % 7 + 1

    # 3. 基礎 XP 計算
    if cycle_day == 7:
        earned_xp = 50
    elif 3 <= cycle_day <= 6:
        earned_xp = 20
    else:
        earned_xp = 10

    # 4. 特別 Bonus: 每 10 次
    new_total_checkins = db.query(Checkin).filter(Checkin.user_id == uid).count() + 1
    has_ten_bonus = False
    if new_total_checkins % 10 == 0:
        earned_xp += 50
        has_ten_bonus = True

    # 5. 特別 Bonus: 月全勤 (100 XP)
    has_monthly_bonus = False
    _, last_day_of_month = calendar.monthrange(today.year, today.month)

    if today.day == last_day_of_month:
        first_day = today.replace(day=1)
        # 注意：這裡要算入「今天這一次」，所以 count 要 +1 或檢查條件包含 today
        monthly_count = db.query(Checkin).filter(
            Checkin.user_id == uid,
            Checkin.checkin_date >= first_day,
            Checkin.checkin_date < today # 查今天以前的
        ).count() + 1

        if monthly_count == last_day_of_month:
            earned_xp += 100
            has_monthly_bonus = True

    # 6. 寫入與更新
    new_checkin = Checkin(
        user_id=uid,
        checkin_date=today,
        streak_count=streak_count,
        total_checkins=new_total_checkins,
        earned_xp=earned_xp
    )
    db.add(new_checkin)
    current_user.xp += earned_xp

    db.commit()
    db.refresh(new_checkin)

    return {
        "streak_count": streak_count,
        "cycle_day": cycle_day,
        "total_checkins": new_total_checkins,
        "earned_xp": earned_xp,
        "show_bonus_modal": has_ten_bonus,
        "show_monthly_bonus": has_monthly_bonus, # 多傳一個旗標給前端
        "is_checked_in_today": True,
        "checkin_date": new_checkin.checkin_date
    }

@router.get("/status", response_model=schemas.CheckinStatus)
def get_checkin_status(
    current_user: Member = Depends(get_current_user),
    db: Session = Depends(get_db)):

    uid = current_user.user_id
    today = date.today()
    yesterday = today - timedelta(days=1)

    # 1. 獲取紀錄
    record = db.query(Checkin).filter(Checkin.user_id == uid, Checkin.checkin_date == today).first()
    last = db.query(Checkin).filter(Checkin.user_id == uid, Checkin.checkin_date == yesterday).first()
    
    # 2. 決定目前「UI 要亮到第幾格」(1~7)
    if record:
        # 今天領過了，顯示今天的循環位置
        ui_cycle_day = (record.streak_count - 1) % 7 + 1
    elif last:
        # 今天還沒領，但昨天有領，亮到昨天的位置
        ui_cycle_day = (last.streak_count - 1) % 7 + 1
    else:
        # 斷掉了或是新用戶，格子全暗
        ui_cycle_day = 0

    # 3. 決定「今天點下去能領多少」(按鈕上的文字)
    # 邏輯：如果今天領過就是 0，沒領過則看 target_day (1-7)
    if record:
        predicted_today_xp = 0
    else:
        # 計算如果今天簽下去，會是循環中的第幾天
        target_streak = last.streak_count + 1 if last else 1
        target_cycle_day = (target_streak - 1) % 7 + 1
        
        if target_cycle_day == 7:
            predicted_today_xp = 50
        elif 3 <= target_cycle_day <= 6:
            predicted_today_xp = 20
        else:
            predicted_today_xp = 10

    # 4. 固定 7 天的獎勵預覽 (讓前端直接 map 渲染 7 個格子)
    # 這是對齊你新版規則的固定數值
    weekly_previews = [10, 10, 20, 20, 20, 20, 50]

    return {
        "has_checked_in": bool(record),
        "current_cycle_day": ui_cycle_day,     # 告訴前端：亮到第幾格
        "today_xp_reward": predicted_today_xp, # 告訴前端：按鈕顯示 +10 或 +20...
        "weekly_rewards": weekly_previews      # 告訴前端：這 7 格分別代表多少錢
    }