from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import outerjoin
from web_app.database import get_db
from web_app.models import Member,MissCardsLibrary, AchCard
from web_app.schemas.gamification import card as schemas
from web_app.dependencies import get_current_user

router = APIRouter()

@router.get("/collection", response_model=list[schemas.CardDisplay])
def get_user_collection(
    current_user: Member=Depends(get_current_user), 
    db: Session = Depends(get_db)):
    # 這裡需要 Left Join: Library LEFT JOIN AchCard
    # 這樣才能顯示出「用戶還沒獲得」的卡片
    
    results = db.query(MissCardsLibrary, AchCard)\
        .outerjoin(AchCard, (MissCardsLibrary.lib_id == AchCard.lib_id) & (AchCard.user_id == current_user.user_id))\
        .filter(MissCardsLibrary.type.in_(['CARD', 'ACHIEVEMENT']))\
        .all()
        
    display_list = []
    for lib, ach in results:
        is_owned = ach is not None and ach.is_unlocked
        
        # 隱藏卡邏輯：如果是隱藏卡且未獲得，不顯示或顯示特殊圖案
        if lib.is_hidden and not is_owned:
            continue # 或顯示為神祕項目
            
        display_list.append({
            "lib_id": lib.lib_id,
            "title": lib.title if is_owned else "???",
            "type": lib.type,
            "series_name": lib.series_name,
            "image_url": lib.image_url if is_owned else "locked.png",
            "is_owned": is_owned,
            "is_hidden": lib.is_hidden,
            "description": lib.description if is_owned else "解鎖後查看",
            "current_val": ach.current_val if ach else 0,
            "target_val": lib.target_val
        })
        
    return display_list