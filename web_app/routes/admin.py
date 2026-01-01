from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Member
# 這裡應該引入你的守門員 (例如 check_admin_access)

router = APIRouter(prefix="/admin", tags=["管理員後台"])

@router.get("/users")
async def get_all_users(db: Session = Depends(get_db)):
    """
    管理員功能：查看系統內所有註冊會員
    """
    # 未來這裡會加入 Depends(admin_required) 檢查 role 是否為 'admin'
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