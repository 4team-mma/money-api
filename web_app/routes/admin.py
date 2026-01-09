from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db
from ..models import Member, AddRecord, Account

router = APIRouter()

@router.get("/users")
async def get_all_users(db: Session = Depends(get_db)):
    """
    管理員功能：查看系統內所有註冊會員
    """
    users = db.query(Member).all()
    return users

@router.delete("/users/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    """
    管理員功能：刪除違規會員
    """
    user = db.query(Member).filter(Member.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到該會員")
    
    db.delete(user)
    db.commit()
    return {"msg": f"會員 {user_id} 已成功刪除"}

@router.get("/stats/rankings")
async def get_admin_rankings(db: Session = Depends(get_db)):
    """
    獲取後台排行榜：僅限一般用戶(role='user')，包含帳號與暱稱
    """
    try:
        # 1. 💰 各路財神消費榜 (類別消費總額排名 - 與用戶身分無關，維持類別統計)
        category_ranks = db.query(
            AddRecord.add_class,
            func.sum(AddRecord.add_amount).label("total_amount")
        ).filter(AddRecord.add_type == False) \
         .group_by(AddRecord.add_class) \
         .order_by(func.sum(AddRecord.add_amount).desc()).all()

        # 2. ✍️ 勤勞小蜜蜂獎 (記帳頻率排名 - 排除 admin)
        frequency_ranks = db.query(
            Member.username,
            Member.name,
            func.count(AddRecord.add_id).label("count")
        ).join(AddRecord, Member.user_id == AddRecord.user_id) \
         .filter(Member.role == 'user') \
         .group_by(Member.user_id) \
         .order_by(func.count(AddRecord.add_id).desc()).limit(5).all()

        # 3. 🛡️ 金庫大總管 (帳戶餘額儲蓄榜 - 排除 admin)
        savings_ranks = db.query(
            Member.username,
            Member.name,
            func.sum(Account.current_balance).label("total_balance")
        ).join(Account, Member.user_id == Account.user_id) \
         .filter(Member.role == 'user') \
         .group_by(Member.user_id) \
         .order_by(func.sum(Account.current_balance).desc()).limit(5).all()

        # 4. 🆙 修仙進度表 (等級 XP 成長榜 - 排除 admin)
        xp_ranks = db.query(
            Member.username, 
            Member.name, 
            Member.xp, 
            Member.level
        ).filter(Member.role == 'user') \
         .order_by(Member.xp.desc()).limit(5).all()

        # 5. 🏆 財富英雄榜 (Top Spenders - 這是你原本畫面最上方的大表資料)
        top_spenders = db.query(
            Member.username,
            Member.name,
            func.sum(AddRecord.add_amount).label("total_spent"),
            func.count(AddRecord.add_id).label("tx_count")
        ).join(AddRecord, Member.user_id == AddRecord.user_id) \
         .filter(Member.role == 'user', AddRecord.add_type == False) \
         .group_by(Member.user_id) \
         .order_by(func.sum(AddRecord.add_amount).desc()).limit(10).all()

        return {
            "category_spending": [{"name": r.add_class, "value": float(r.total_amount)} for r in category_ranks],
            "active_bees": [{"username": r.username, "name": r.name, "value": r.count, "role": "user"} for r in frequency_ranks],
            "wealth_masters": [{"username": r.username, "name": r.name, "value": float(r.total_balance), "role": "user"} for r in savings_ranks],
            "xp_immortals": [{"username": r.username, "name": r.name, "value": r.xp, "level": r.level, "role": "user"} for r in xp_ranks],
            "top_spenders": [
                {
                    "username": r.username, 
                    "name": r.name, 
                    "totalSpent": float(r.total_spent), 
                    "transactions": r.tx_count,
                    "avgSpent": float(r.total_spent / r.tx_count) if r.tx_count > 0 else 0,
                    "role": "user"
                } for r in top_spenders
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))