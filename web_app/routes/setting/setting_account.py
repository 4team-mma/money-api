# web_app/routers/setting/setting_account.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from ...database import get_db
from ...models import Member,LoginActivity
from ...schemas.setting_login import LoginActivityRead
from ...schemas.member import NotionConfigUpdate
from ...dependencies import get_current_user
from ...utils.ai_security import encrypt_api_key


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



@router.patch("/notion-config")
async def update_notion_config(
    data: NotionConfigUpdate, 
    current_user: Member = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 🌟 正確的 PATCH 處理：只抓取前端「確實有傳遞」的欄位
    update_data = data.model_dump(exclude_unset=True)
    
    if "notion_api_key" in update_data:
        api_key = update_data["notion_api_key"]
        if api_key: # 如果有值，就加密存入
            current_user.notion_api_key = encrypt_api_key(api_key)
        else:       # 如果前端傳 null 或空字串，就清空 (解除綁定)
            current_user.notion_api_key = None
            
    if "notion_page_id" in update_data:
        page_id = update_data["notion_page_id"]
        current_user.notion_page_id = page_id if page_id else None
        
    db.commit()
    db.refresh(current_user)
    return {"message": "Notion 設定已更新喵！"}
