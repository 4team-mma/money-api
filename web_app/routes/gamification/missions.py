from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime
import random
from typing import List
from web_app.database import get_db
from web_app.models import DailyMission, MissCardsLibrary, Member, AchCard
from web_app.schemas.gamification import mission as schemas
from web_app.dependencies import get_current_user
from sqlalchemy import func

router = APIRouter()

@router.get("/today", response_model=List[schemas.MissionDisplay])
def get_daily_missions(current_user: Member = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    uid = current_user.user_id
    
    # 抓取該用戶「今天」的所有任務紀錄，確保槽位固定不重生
    all_today_missions = db.query(DailyMission, MissCardsLibrary).join(
        MissCardsLibrary, DailyMission.lib_id == MissCardsLibrary.lib_id
    ).filter(
        DailyMission.user_id == uid, 
        DailyMission.created_at == today
    ).all()

    occupied_slots = [m[0].slot_num for m in all_today_missions if m[0].slot_num is not None]
    
    if len(all_today_missions) < 3:
        available_slots = [s for s in [1, 2, 3] if s not in occupied_slots]
        needed = len(available_slots)
        
        if needed > 0:
            active_lib_ids = [m[0].lib_id for m in all_today_missions]
            # 排除稀有標題，防止隨機抽取到挑戰任務
            ex_titles = ['守護長老：金字塔貓', '幻夢領袖：獨角獸貓', '戰神：狂暴山貓', '永恆智者：宇宙貓', '智慧的洞察', '極限的挑戰', '夢想的積累', '紀律的試煉']
            query = db.query(MissCardsLibrary).filter(MissCardsLibrary.type == 'MISSION', ~MissCardsLibrary.title.in_(ex_titles))
            if active_lib_ids: 
                query = query.filter(~MissCardsLibrary.lib_id.in_(active_lib_ids))
            
            pool = query.all()
            if pool:
                temp_pool = list(pool)
                for _ in range(min(needed, len(temp_pool))):
                    pick = random.choice(temp_pool)
                    db.add(DailyMission(user_id=uid, lib_id=pick.lib_id, created_at=today, current_val=0, miss_status=0, slot_num=available_slots.pop(0)))
                    temp_pool.remove(pick)
                db.commit()
                return get_daily_missions(current_user, db)

    result = []
    for dm, lib in all_today_missions:
        result.append({
            "miss_id": dm.miss_id, "title": lib.title, "difficulty": lib.difficulty, "category": lib.category, "description": lib.description, 
            "xp_reward": lib.xp_reward, "current_val": dm.current_val, "target_val": lib.target_val, "miss_status": dm.miss_status, 
            "slot_num": dm.slot_num if dm.slot_num is not None else 0, "has_card_reward": lib.card_reward_id is not None
        })
    return sorted(result, key=lambda x: x["slot_num"])

@router.post("/{miss_id}/accept")
def accept_mission(miss_id: int, current_user: Member = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.query(DailyMission).filter(DailyMission.miss_id == miss_id, DailyMission.user_id == current_user.user_id).first()
    if m is None: 
        raise HTTPException(status_code=404, detail="找不到任務")
    m.miss_status = 1
    db.commit()
    return {"message": "接取成功"}

@router.post("/{miss_id}/claim", response_model=schemas.ClaimRewardResponse)
def claim_mission_reward(miss_id: int, current_user: Member = Depends(get_current_user), db: Session = Depends(get_db)):
    mission = db.query(DailyMission).filter(DailyMission.miss_id == miss_id, DailyMission.user_id == current_user.user_id).first()
    if not mission: 
        raise HTTPException(status_code=404, detail="任務不存在")
    
    lib = db.query(MissCardsLibrary).filter(MissCardsLibrary.lib_id == mission.lib_id).first()
    if lib is None:
        raise HTTPException(status_code=404, detail="定義遺失")
    
    current_user.xp += lib.xp_reward
    card_msg = ""
    
    # 卡牌解鎖邏輯
    if lib.card_reward_id is not None:
        reward_id = lib.card_reward_id
        existing = db.query(AchCard).filter(AchCard.user_id == current_user.user_id, AchCard.lib_id == reward_id).first()
        if existing:
            if not existing.is_unlocked:
                existing.is_unlocked = True
                existing.unlocked_at = datetime.now()
                card_msg = "解鎖成功！"
            else:
                current_user.points += 50
                card_msg = "已擁有，獎勵 50 金幣"
        else:
            db.add(AchCard(user_id=current_user.user_id, lib_id=reward_id, is_unlocked=True, unlocked_at=datetime.now()))
            card_msg = "獲得新卡牌！"
        db.flush()

    # 稀有任務遞補邏輯
    rare_mission_map = {'理財初心者': '紀律的試煉', '節流冒險者': '夢想的積累', '投資先鋒': '極限的挑戰', '財富領主': '智慧的洞察'}
    rare_titles = list(rare_mission_map.values())
    current_series = (lib.series_name or "").strip()
    is_rare_triggered = False

    if lib.title not in rare_titles and current_series in rare_mission_map:
        owned_count = db.query(AchCard).join(MissCardsLibrary, AchCard.lib_id == MissCardsLibrary.lib_id).filter(
            AchCard.user_id == current_user.user_id,
            MissCardsLibrary.series_name == current_series,
            AchCard.is_unlocked == True,
            MissCardsLibrary.difficulty != 'RARE'
        ).count()

        if owned_count >= 4:
            target_title = rare_mission_map[current_series]
            rare_lib = db.query(MissCardsLibrary).filter(MissCardsLibrary.title == target_title, MissCardsLibrary.type == 'MISSION').first()
            if rare_lib is not None:
                mission.lib_id = rare_lib.lib_id
                mission.miss_status = 0
                mission.current_val = 0
                card_msg += f" | 已開啟挑戰：{target_title}"
                is_rare_triggered = True

    if not is_rare_triggered:
        mission.miss_status = 2
    
    db.commit()
    return {
        "message": "領取成功", 
        "earned_xp": lib.xp_reward, 
        "new_level": current_user.level, 
        "new_balance_xp": current_user.xp, 
        "card_reward": card_msg if card_msg else None
    }

@router.post("/trigger/{action_code}")
def trigger_mission_action(action_code: str, current_user: Member = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    統一瀏覽型任務觸發器：嚴格要求必須是「已接取 (status=1)」
    """
    action_map = {
        "view_accounts": "資產確認",
        "view_charts_pie_inn": "圖表分析",
        "view_charts_pie_exp": "月度結算",
        "view_calendar": "回顧過去",
        "view_trends": "溫故知新",
        "view_salary": "了解行情",
        "view_targets": "設定目標",
        "change_theme": "品味生活"
    }
    
    target_title = action_map.get(action_code)
    if not target_title:
        return {"status": "error", "message": "未知行為代碼"}

    # 僅針對「修煉中 (status=1)」的對應任務進行進度補滿
    mission_record = db.query(DailyMission).join(
        MissCardsLibrary, DailyMission.lib_id == MissCardsLibrary.lib_id
    ).filter(
        DailyMission.user_id == current_user.user_id,
        MissCardsLibrary.title == target_title,
        DailyMission.miss_status == 1
    ).first()

    if mission_record:
        lib = db.query(MissCardsLibrary).filter(MissCardsLibrary.lib_id == mission_record.lib_id).first()
        target_val = lib.target_val if lib else 1
        
        if mission_record.current_val < target_val:
            mission_record.current_val = target_val
            db.commit()
            return {"status": "updated", "mission": target_title}
    
    return {"status": "skipped", "reason": "無對應修煉中任務"}