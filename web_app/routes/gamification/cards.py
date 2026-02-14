from fastapi import APIRouter, Depends, Request  # <--- 加入 Request
from sqlalchemy.orm import Session
from sqlalchemy import outerjoin
from web_app.database import get_db
from web_app.models import Member, MissCardsLibrary, AchCard
from web_app.schemas.gamification import card as schemas
from web_app.dependencies import get_current_user

router = APIRouter()

@router.get("/collection", response_model=list[schemas.CardDisplay])
def get_user_collection(
    request: Request,  # <--- 注入 Request 以取得 Base URL
    current_user: Member = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    results = db.query(MissCardsLibrary, AchCard)\
        .outerjoin(AchCard, (MissCardsLibrary.lib_id == AchCard.lib_id) & (AchCard.user_id == current_user.user_id))\
        .filter(MissCardsLibrary.type.in_(['CARD', 'ACHIEVEMENT']))\
        .all()
        
    display_list = []
    
    # 取得基礎 URL (例如 http://127.0.0.1:8000/)
    base_url = str(request.base_url).rstrip("/")
    
    for lib, ach in results:
        is_owned = ach is not None and ach.is_unlocked
        
        # 處理圖片 URL
        # 假設 DB 裡的 lib.image_url 存的是檔名 (如 "ENTJ.png" 或 "NT_SP01.png")
        # 假設 lib.series_name 是資料夾名稱 (如 "NT", "SJ")
        
        final_image_url = None
        
        if is_owned:
            if lib.image_url:
                # 拼接完整路徑: http://.../static/images/{Group}/{Filename}
                # 這裡對應第一步 mount 的路徑
                final_image_url = f"{base_url}/static/images/{lib.series_name}/{lib.image_url}"
            else:
                # 若 DB 沒存圖片，這是一個後端資料缺失的警訊
                final_image_url = f"{base_url}/static/images/placeholder.png"
        else:
            # 未獲得時顯示鎖頭圖 (請確保你有 locked.png)
            final_image_url = None 

        # 隱藏卡邏輯
        if lib.is_hidden and not is_owned:
            continue
            
        display_list.append({
            "lib_id": lib.lib_id,
            "title": lib.title, # 不要在這裡改 ???，前端會根據 is_owned 處理顯示邏輯
            "type": lib.type,
            "series_name": lib.series_name,
            "image_url": final_image_url, # 這裡回傳的是真實可連線的 URL
            "is_owned": is_owned,
            "is_hidden": lib.is_hidden,
            "description": lib.description,
            "current_val": ach.current_val if ach else 0,
            "target_val": lib.target_val
        })
        
    return display_list