from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta
from web_app.database import get_db # 假設你的 db session 在這裡
from web_app.models import Checkin, Member, Setting
from web_app.schemas.gamification import checkin as schemas
from web_app.dependencies import get_current_user

router = APIRouter()



@router.post("/action", response_model=schemas.CheckinResponse)
def perform_checkin(
    current_user:Member=Depends(get_current_user),
    db: Session = Depends(get_db)):
    
    uid = current_user.user_id
    today = date.today()
        # 1. 檢查今天是否已打卡
    existing = db.query(Checkin).filter(
        
        Checkin.user_id == uid,
        Checkin.checkin_date == today
    ).first()
    
    if existing:
        return existing

    # 2. 計算連續天數 (找昨天的紀錄)
    yesterday = today - timedelta(days=1)
    last_record = db.query(Checkin).filter(
        Checkin.user_id == uid,
        Checkin.checkin_date == yesterday
    ).first()

    streak = last_record.streak_count + 1 if last_record else 1
    
    # 3. 計算 XP (這裡可以設計公式，例如連續7天加成)
    base_xp = 10
    bonus_xp = 100 if streak % 7 == 0 else 0
    total_xp_reward = base_xp + bonus_xp

    # 需先查詢總次數，這裡簡化邏輯直接 +1 
    current_total = db.query(Checkin).filter(Checkin.user_id == uid).count()
    # 4. 寫入資料庫
    new_checkin = Checkin(
        user_id=uid,
        checkin_date=today,
        streak_count=streak,
        total_checkins=current_total + 1,
        earned_xp=total_xp_reward
    )
    db.add(new_checkin)
    
    # 5. 更新會員 XP
    
    if not current_user:
        raise HTTPException(status_code=404, detail="找不到該會員資料")
    
    current_user.xp += total_xp_reward
    # TODO: 這裡可以呼叫育育寫的「升級判斷函式」
    
    db.commit()
    db.refresh(new_checkin)
    return new_checkin
    

# 取得當前狀態
@router.get("/status", response_model=schemas.CheckinStatus)
def get_checkin_status(
    current_user: Member=Depends(get_current_user), 
    db: Session = Depends(get_db)):
    uid = current_user.user_id
    today = date.today()
    record = db.query(Checkin).filter(Checkin.user_id == uid, Checkin.checkin_date == today).first()
    
    # 查詢目前連續天數
    last = db.query(Checkin).filter(Checkin.user_id == uid).order_by(Checkin.checkin_date.desc()).first()
    streak = last.streak_count if last else 0
    
    return {
        "has_checked_in": bool(record),
        "streak": streak,
        "today_xp_reward": 10 # 這裡可改為動態計算
    }