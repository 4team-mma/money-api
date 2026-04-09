from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from ...database import get_db
from ...models import Member,LoginActivity
from ...schemas.setting_login import LoginActivityRead
from ...dependencies import get_current_user

router = APIRouter()

@router.get("/login-activities",
        response_model=List[LoginActivityRead],
        summary="🔍 取得我的最近登入活動(請先登入帳號在測試)",
        description="回傳當前登入使用者最近 5 筆的登入紀錄，包含 IP、裝置資訊與登入時間。"
        )
def get_my_login_activities(
    db: Session = Depends(get_db),
    current_user: Member=Depends(get_current_user)
):
    user_id = current_user.user_id
    # 抓取最近 5 筆登入紀錄
    activities = db.query(LoginActivity).filter(
        LoginActivity.user_id == user_id
    ).order_by(LoginActivity.login_at.desc()).limit(5).all()

    return activities
