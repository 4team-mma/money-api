# 這是misscards_library

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date,datetime
import random
from web_app.database import get_db
from web_app.models import DailyMission, MissCardsLibrary, Member, AchCard
from web_app.schemas.gamification import mission as schemas
from web_app.dependencies import get_current_user

router = APIRouter()

@router.get("/today", response_model=list[schemas.MissionDisplay])
def get_daily_missions(
    current_user: Member=Depends(get_current_user), 
    db: Session = Depends(get_db)):
    today = date.today()
    
    
    # 1. 查詢今天是否已分配任務
    missions = db.query(DailyMission, MissCardsLibrary)\
        .join(MissCardsLibrary, DailyMission.lib_id == MissCardsLibrary.lib_id)\
        .filter(DailyMission.user_id == current_user.user_id, DailyMission.created_at == today)\
        .all()
    
    # 2. 如果今天還沒分配，則隨機生成 3 個
    if not missions:
        # 從 Library 撈出所有類型為 MISSION 的
        all_mission_defs = db.query(MissCardsLibrary).filter(MissCardsLibrary.type == 'MISSION').all()
        
        # 排除用戶已經「做過且不能重複做」的 (視規則而定，這裡假設每日任務可重複)
        # 隨機選 3 個
        selected = random.sample(all_mission_defs, min(3, len(all_mission_defs)))
        
        new_missions = []
        for idx, m_def in enumerate(selected):
            dm = DailyMission(
                user_id=current_user.user_id,
                lib_id=m_def.lib_id,
                slot_num=idx + 1,
                created_at=today,
                current_val=0,
                miss_status=0 
            )
            db.add(dm)
            new_missions.append(dm)
        db.commit()
        
        # 重新查詢以獲得 Join 資料
        return get_daily_missions(current_user, db)

    # 3. 整理回傳格式
    result = []
    for dm, library in missions:
        result.append({
            "miss_id": dm.miss_id,
            "title": library.title,
            "difficulty": library.difficulty,
            "category": library.category,
            "xp_reward": library.xp_reward,
            "current_val": dm.current_val,
            "target_val": library.target_val,
            "miss_status": dm.miss_status,
            "slot_num": dm.slot_num
        })
    return result

@router.post("/{miss_id}/claim", response_model=schemas.ClaimRewardResponse)
def claim_mission_reward(
    miss_id: int, 
    current_user: Member=Depends(get_current_user), 
    db: Session = Depends(get_db)):
    # 1. 找任務
    mission = db.query(DailyMission).filter(DailyMission.miss_id == miss_id, DailyMission.user_id == current_user.user_id).first()
    if not mission:
        raise HTTPException(status_code=404, detail="任務不存在")
    
    if mission.miss_status != 1: # 1: 待領取
        raise HTTPException(status_code=400, detail="任務尚未完成或已領取")
        
    library_item = db.query(MissCardsLibrary).filter(MissCardsLibrary.lib_id == mission.lib_id).first()
    
    # 【修正點 2】檢查 Library 資料是否存在
    if not library_item:
        raise HTTPException(status_code=404, detail="任務定義資料遺失")
    
    # 2. 發放 XP (✅ 直接操作 current_user)
    current_user.xp += library_item.xp_reward
    
    # 3. 發放卡牌 (如果有)
    card_msg = None
    if library_item.card_reward_id:
        # 檢查是否已擁有
        existing_card = db.query(AchCard).filter(AchCard.user_id == current_user.user_id, AchCard.lib_id == library_item.card_reward_id).first()
        if not existing_card:
            new_card = AchCard(
                user_id=current_user.user_id, 
                lib_id=library_item.card_reward_id, 
                is_unlocked=True, 
                unlocked_at=datetime.now())
            db.add(new_card)
            card_msg = "獲得隱藏卡牌！"
        else:
            card_msg = "卡牌已擁有，轉換為 50 金幣"
            current_user.points += 50 
            

    # 4. 更新任務狀態
    mission.miss_status = 2 # 已領取
    db.commit()
    
    return {
        "message": "領取成功",
        "earned_xp": library_item.xp_reward,
        "new_level": current_user.level, # 需實作等級邏輯
        "new_balance_xp": current_user.xp,
        "card_reward": card_msg
    }