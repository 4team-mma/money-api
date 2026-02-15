from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, timedelta
import calendar  # 🌟 Julia 的需求：計算月份天數用
from web_app.database import get_db
from web_app.models import Checkin, Member
from web_app.schemas.gamification import checkin as schemas
from web_app.dependencies import get_current_user
from web_app.services.game_service import GameService # 🌟 你的需求：掃描任務進度

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
        raise HTTPException(status_code=400, detail="今天已經打過卡囉！")

    # 2. 連續天數與循環邏輯 (Julia 的動態計算)
    yesterday = today - timedelta(days=1)
    last_record = db.query(Checkin).filter(Checkin.user_id == uid, Checkin.checkin_date == yesterday).first()

    streak_count = last_record.streak_count + 1 if last_record else 1
    cycle_day = (streak_count - 1) % 7 + 1

    # 3. 基礎 XP 計算 (對齊 Excel 規則)
    if cycle_day == 7:
        earned_xp = 50
    elif 3 <= cycle_day <= 6:
        earned_xp = 20
    else:
        earned_xp = 10

    # 4. 特別 Bonus: 每累積 10 次簽到額外加 50
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
        monthly_count = db.query(Checkin).filter(
            Checkin.user_id == uid,
            Checkin.checkin_date >= first_day,
            Checkin.checkin_date < today
        ).count() + 1

        if monthly_count == last_day_of_month:
            earned_xp += 100
            has_monthly_bonus = True

    # 6. 寫入與更新資料庫
    new_checkin = Checkin(
        user_id=uid,
        checkin_date=today,
        streak_count=streak_count,
        total_checkins=new_total_checkins,
        earned_xp=earned_xp
    )
    db.add(new_checkin)
    current_user.xp += earned_xp

    # 🌟 7. 你的全域掃描器：觸發「每日報到」任務 (Category='系統')
    GameService.update_mission_progress(
        db, 
        user_id=current_user.user_id, 
        category='系統'
    )

    db.commit()
    db.refresh(new_checkin)

    return {
        "streak_count": streak_count,
        "cycle_day": cycle_day,
        "total_checkins": new_total_checkins,
        "earned_xp": earned_xp,
        "show_bonus_modal": has_ten_bonus,
        "show_monthly_bonus": has_monthly_bonus,
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

    record = db.query(Checkin).filter(Checkin.user_id == uid, Checkin.checkin_date == today).first()
    last = db.query(Checkin).filter(Checkin.user_id == uid, Checkin.checkin_date == yesterday).first()
    
    # 決定 UI 要亮到第幾格
    if record:
        ui_cycle_day = (record.streak_count - 1) % 7 + 1
    elif last:
        ui_cycle_day = (last.streak_count - 1) % 7 + 1
    else:
        ui_cycle_day = 0

    # 預測今日領取金額
    target_streak = last.streak_count + 1 if last else 1
    target_cycle_day = (target_streak - 1) % 7 + 1
    
    if target_cycle_day == 7:
        predicted_xp = 50
    elif 3 <= target_cycle_day <= 6:
        predicted_xp = 20
    else:
        predicted_xp = 10

    return {
        "has_checked_in": bool(record),
        "current_cycle_day": ui_cycle_day,
        "today_xp_reward": 0 if record else predicted_xp,
        "weekly_rewards": [10, 10, 20, 20, 20, 20, 50]
    }