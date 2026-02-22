from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from web_app.database import get_db
from web_app.models import Member, MissCardsLibrary, AchCard
from web_app.schemas.gamification import card as schemas
from web_app.dependencies import get_current_user

router = APIRouter()

@router.get("/collection", response_model=list[schemas.CardDisplay])
def get_user_collection(
    request: Request,
    current_user: Member = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    results = db.query(MissCardsLibrary, AchCard)\
        .outerjoin(AchCard, (MissCardsLibrary.lib_id == AchCard.lib_id) & (AchCard.user_id == current_user.user_id))\
        .filter(MissCardsLibrary.type.in_(['CARD', 'ACHIEVEMENT']))\
        .all()
        
    display_list = []
    
    for lib, ach in results:
        is_owned = ach is not None and ach.is_unlocked
        
        final_image_url = None
        if lib.image_url:
            if lib.image_url.startswith("http"):
                final_image_url = lib.image_url
            elif is_owned:
                base_url = str(request.base_url).rstrip("/")
                final_image_url = f"{base_url}/static/images/{lib.category}/{lib.image_url}"

        if lib.is_hidden and not is_owned:
            continue
        print(f"DEBUG: 處理卡片 {lib.title}, 難度: {lib.difficulty}, 是否擁有: {is_owned}") # 🌟 觀察 Console
        
        display_list.append({
            "lib_id": lib.lib_id,
            "title": lib.title,
            "type": lib.type,
            "difficulty": lib.difficulty, # 🌟 關鍵修正：必須回傳難度，前端才找得到 Rare 卡！
            "category": lib.category,
            "series_name": lib.series_name,
            "image_url": final_image_url,
            "is_owned": is_owned,
            "is_hidden": lib.is_hidden,
            "description": lib.description,
            "current_val": ach.current_val if ach else 0,
            "target_val": lib.target_val
        })
        
    return display_list