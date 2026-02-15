from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime
import random
from typing import List
from web_app.database import get_db
from web_app.models import DailyMission, MissCardsLibrary, Member, AchCard
from web_app.schemas.gamification import mission as schemas
from web_app.dependencies import get_current_user

router = APIRouter()

@router.get("/today", response_model=List[schemas.MissionDisplay])
def get_daily_missions(current_user: Member = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    uid = current_user.user_id
    existing_missions = db.query(DailyMission, MissCardsLibrary).join(MissCardsLibrary, DailyMission.lib_id == MissCardsLibrary.lib_id).filter(DailyMission.user_id == uid, MissCardsLibrary.type == 'MISSION', ((DailyMission.miss_status == 1) | (DailyMission.created_at == today))).all()

    if len(existing_missions) < 3:
        occupied_slots = [r[0] for r in db.query(DailyMission.slot_num).filter(DailyMission.user_id == uid, DailyMission.created_at == today).all()]
        available_slots = [s for s in [1, 2, 3] if s not in occupied_slots]
        needed = len(available_slots)
        if needed > 0:
            done_ids = [r[0] for r in db.query(DailyMission.lib_id).filter(DailyMission.user_id == uid, DailyMission.miss_status == 2).all()]
            active_ids = [m[0].lib_id for m in existing_missions]
            exclude_ids = list(set(done_ids + active_ids))
            ex_titles = ['守護長老：金字塔貓', '幻夢領袖：獨角獸貓', '戰神：狂暴山貓', '永恆智者：宇宙貓']
            query = db.query(MissCardsLibrary).filter(MissCardsLibrary.type == 'MISSION', ~MissCardsLibrary.title.in_(ex_titles))
            if exclude_ids: query = query.filter(~MissCardsLibrary.lib_id.in_(exclude_ids))
            pool = query.all()
            if pool:
                def get_w(m):
                    w = {'EASY': 5.0, 'NORMAL': 2.0, 'HARD': 0.5}.get(m.difficulty, 1.0)
                    return w * 0.3 if m.card_reward_id else w
                temp_pool = list(pool)
                for _ in range(min(needed, len(temp_pool))):
                    ws = [get_w(m) for m in temp_pool]
                    pick = random.choices(temp_pool, weights=ws, k=1)[0]
                    db.add(DailyMission(user_id=uid, lib_id=pick.lib_id, created_at=today, current_val=0, miss_status=0, slot_num=available_slots.pop(0)))
                    temp_pool.remove(pick)
                db.commit()
                return get_daily_missions(current_user, db)

    result = []
    for dm, lib in existing_missions:
        if dm is not None and lib is not None:
            result.append({"miss_id": dm.miss_id, "title": lib.title, "difficulty": lib.difficulty, "category": lib.category, "description": lib.description, "xp_reward": lib.xp_reward, "current_val": dm.current_val, "target_val": lib.target_val, "miss_status": dm.miss_status, "slot_num": dm.slot_num or 0, "has_card_reward": lib.card_reward_id is not None})
    return sorted(result, key=lambda x: x["slot_num"])

@router.post("/{miss_id}/accept")
def accept_mission(miss_id: int, current_user: Member = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.query(DailyMission).filter(DailyMission.miss_id == miss_id, DailyMission.user_id == current_user.user_id).first()
    if m is None: raise HTTPException(status_code=404, detail="找不到任務")
    m.miss_status = 1
    db.commit()
    return {"message": "接取成功"}

@router.post("/{miss_id}/abandon")
def abandon_mission(miss_id: int, current_user: Member = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.query(DailyMission).filter(DailyMission.miss_id == miss_id, DailyMission.user_id == current_user.user_id).first()
    if m is None: raise HTTPException(status_code=404, detail="找不到任務")
    db.delete(m)
    db.commit()
    return {"message": "已放棄任務"}

@router.post("/{miss_id}/claim", response_model=schemas.ClaimRewardResponse)
def claim_mission_reward(miss_id: int, current_user: Member = Depends(get_current_user), db: Session = Depends(get_db)):
    mission = db.query(DailyMission).filter(DailyMission.miss_id == miss_id, DailyMission.user_id == current_user.user_id).first()
    if mission is None: raise HTTPException(status_code=404, detail="任務不存在")
    lib = db.query(MissCardsLibrary).filter(MissCardsLibrary.lib_id == mission.lib_id).first()
    if lib is None: raise HTTPException(status_code=404, detail="定義遺失")
    
    current_user.xp += lib.xp_reward
    card_msg = None
    if lib.card_reward_id is not None:
        existing = db.query(AchCard).filter(AchCard.user_id == current_user.user_id, AchCard.lib_id == lib.card_reward_id).first()
        if existing is None:
            db.add(AchCard(user_id=current_user.user_id, lib_id=lib.card_reward_id, is_unlocked=True, unlocked_at=datetime.now()))
            card_msg = "獲得新卡牌獎勵！"
        else:
            current_user.points += 50
            card_msg = "卡牌已擁有，轉換為 50 金幣"

    mission.miss_status = 2
    
    # 🌟 稀有卡任務替換邏輯：若投資先鋒集齊 4/4，自動生成極限挑戰
    if lib.series_name == '投資先鋒':
        completed_count = db.query(DailyMission).join(MissCardsLibrary).filter(DailyMission.user_id == current_user.user_id, MissCardsLibrary.series_name == '投資先鋒', DailyMission.miss_status == 2).count()
        if completed_count >= 4:
            rare_task = db.query(MissCardsLibrary).filter(MissCardsLibrary.title == '極限的挑戰').first()
            if rare_task:
                db.add(DailyMission(user_id=current_user.user_id, lib_id=rare_task.lib_id, created_at=date.today(), current_val=0, miss_status=1, slot_num=mission.slot_num))
    
    db.commit()
    return {"message": "領取成功", "earned_xp": lib.xp_reward, "new_level": current_user.level, "new_balance_xp": current_user.xp, "card_reward": card_msg}