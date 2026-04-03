from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date

from web_app.database import get_db
from web_app.models import Member
from web_app.schemas.gamification import summary as schemas
from web_app.dependencies import get_current_user
from web_app.services.game_service import GameService

router = APIRouter()

@router.get("/info")
def get_game_summary(
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    is_updated = False
    while True:
        required = GameService.get_required_xp(current_user.level)
        if current_user.xp >= required and current_user.level < 100:
            current_user.xp -= required
            current_user.level += 1
            is_updated = True
        else:
            break

    if is_updated:
        db.commit() # 把校正後的結果存回去
        db.refresh(current_user)

    # 🌟 邏輯直接交給 Service 計算，出錯會交由全域 Handler 處理
    user_xp = getattr(current_user, 'xp', 0) or 0
    user_level = getattr(current_user, 'level', 1) or 1

    # 調用統一公式獲取門檻
    next_level_threshold = GameService.get_required_xp(user_level)

    return {
        "level": user_level,
        "xp": user_xp,
        "next_level_xp": next_level_threshold,
        "streak_count": getattr(current_user, 'streak_count', 0),
        "has_checked_in": False,
        "username": current_user.username,
        "job": current_user.job or "錢包守門員",
        "points": current_user.points or 0,
        "max_level": 100
    }
