from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db
from ..models import Member, AddRecord, Account
from ..dependencies import admin_required

router = APIRouter(dependencies=[Depends(admin_required)])


@router.get("/users")
async def get_all_users(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    return db.query(Member).offset(skip).limit(limit).all()


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(Member).filter(Member.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到該會員")
    db.delete(user)
    db.commit()
    return {"msg": f"會員 {user_id} 已成功刪除"}


@router.put("/users/{user_id}/block")
async def block_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(Member).filter(Member.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到會員")
    user.status = "banned"
    db.commit()
    return {"msg": f"會員 {user.username} 已被停用"}


@router.get("/stats/rankings")
async def get_admin_rankings(db: Session = Depends(get_db)):
    # 1. 💰 各路財神消費榜 (修正處：補上 .all() 括號)
    category_ranks = (
        db.query(
            AddRecord.add_class, func.sum(AddRecord.add_amount).label("total_amount")
        )
        .filter(AddRecord.add_type == False)
        .group_by(AddRecord.add_class)
        .order_by(func.sum(AddRecord.add_amount).desc())
        .limit(10)
        .all()
    )  # ✅ 這裡補上了 ()

    # 2. ✍️ 勤勞小蜜蜂獎
    frequency_ranks = (
        db.query(
            Member.username, Member.name, func.count(AddRecord.add_id).label("count")
        )
        .join(AddRecord, Member.user_id == AddRecord.user_id)
        .filter(Member.role == "user")
        .group_by(Member.user_id)
        .order_by(func.count(AddRecord.add_id).desc())
        .limit(5)
        .all()
    )

    # 3. 🛡️ 金庫大總管
    savings_ranks = (
        db.query(
            Member.username,
            Member.name,
            func.sum(Account.current_balance).label("total_balance"),
        )
        .join(Account, Member.user_id == Account.user_id)
        .filter(Member.role == "user")
        .group_by(Member.user_id)
        .order_by(func.sum(Account.current_balance).desc())
        .limit(5)
        .all()
    )

    # 4. 🆙 修仙進度表
    xp_ranks = (
        db.query(Member.username, Member.name, Member.xp, Member.level)
        .filter(Member.role == "user")
        .order_by(Member.xp.desc())
        .limit(5)
        .all()
    )

    # 5. 🏆 財富英雄榜
    top_spenders = (
        db.query(
            Member.username,
            Member.name,
            func.sum(AddRecord.add_amount).label("total_spent"),
            func.count(AddRecord.add_id).label("tx_count"),
        )
        .join(AddRecord, Member.user_id == AddRecord.user_id)
        .filter(Member.role == "user", AddRecord.add_type == False)
        .group_by(Member.user_id)
        .order_by(func.sum(AddRecord.add_amount).desc())
        .limit(10)
        .all()
    )

    # 格式化回傳 (加入空值檢查 or 0)
    return {
        "category_spending": [
            {"name": r.add_class, "value": float(r.total_amount or 0)}
            for r in category_ranks
        ],
        "active_bees": [
            {"username": r.username, "name": r.name, "value": r.count, "role": "user"}
            for r in frequency_ranks
        ],
        "wealth_masters": [
            {
                "username": r.username,
                "name": r.name,
                "value": float(r.total_balance or 0),
                "role": "user",
            }
            for r in savings_ranks
        ],
        "xp_immortals": [
            {
                "username": r.username,
                "name": r.name,
                "value": r.xp,
                "level": r.level,
                "role": "user",
            }
            for r in xp_ranks
        ],
        "top_spenders": [
            {
                "username": r.username,
                "name": r.name,
                "totalSpent": float(r.total_spent or 0),
                "transactions": r.tx_count,
                #  修正除以零的判斷邏輯
                "avgSpent": (
                    float(r.total_spent or 0) / r.tx_count
                    if (r.tx_count and r.tx_count > 0)
                    else 0
                ),
                "role": "user",
            }
            for r in top_spenders
        ],
    }
