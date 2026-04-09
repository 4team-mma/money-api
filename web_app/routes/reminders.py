from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from ..database import get_db
from ..models import Member, Notification
from ..schemas.notification import (
    NotificationCreate,
)
from ..dependencies import get_current_user
from datetime import datetime, time

router = APIRouter()

# 取得未讀數量
@router.get("/unread-count")
async def get_unread_count(
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user) # 從 Token 取得身分
):
    count = db.query(func.count(Notification.reminder_id))\
              .filter(
                  Notification.user_id == current_user.user_id, # 確保只看自己的
                  Notification.is_read == False,
                  Notification.is_active == True
              ).scalar()
    return {"unread_count": count or 0}

# 取得通知列表 (供跑馬燈或列表頁使用)
@router.get("/list")
async def get_notifications(db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    now = datetime.now()
    # SQL 過濾：只回傳「日期時間已過」的通知
    notifications = db.query(Notification).filter(
        Notification.user_id == current_user.user_id,
        # (日期 < 今天) OR (日期 == 今天 且 時間 <= 現在)
        or_(
            Notification.reminder_date_start < now.date(),
            and_(
                Notification.reminder_date_start == now.date(),
                Notification.reminder_time <= now.time()
            )
        )
    ).order_by(Notification.created_at.desc()).all()
    return notifications

# 標記特定通知為已讀
@router.patch("/{reminder_id}/read")
async def mark_as_read(
    reminder_id: int,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    notification = db.query(Notification).filter(
        Notification.reminder_id == reminder_id,
        Notification.user_id == current_user.user_id # 安全檢查：只能改自己的
    ).first()

    if not notification:
        raise HTTPException(status_code=404, detail="找不到此通知")

    notification.is_read = True
    db.commit()
    return {"msg": "已標記為已讀"}

@router.patch("/read-all", summary="✅ 全部標記為已讀")
async def mark_all_as_read(
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    # 尋找該使用者所有未讀且啟用的通知
    unread_notifications = db.query(Notification).filter(
        Notification.user_id == current_user.user_id,
        Notification.is_read == False,
        Notification.is_active == True
    ).all()

    if not unread_notifications:
        return {"msg": "沒有未讀通知"}

    # 批次更新狀態
    for note in unread_notifications:
        note.is_read = True

    db.commit()
    return {"msg": f"已將 {len(unread_notifications)} 則通知標記為已讀"}

@router.post("/", summary="⏰ 手動新增提醒", status_code=status.HTTP_201_CREATED)
async def create_manual_reminder(
    data: NotificationCreate, # 確保你的 Schema 包含 title, date, time, description
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    new_note = Notification(
        user_id=current_user.user_id,
        reminder_title=data.reminder_title,
        category="manual", # 固定類別為手動提醒
        description=data.description,
        reminder_date_start=data.reminder_date_start,
        reminder_time=data.reminder_time or time(10, 0), # 預設早上十點
        is_active=True,
        is_read=False
    )
    db.add(new_note)
    db.commit()
    db.refresh(new_note)
    return new_note

@router.delete("/delete-all", summary="🗑️ 清空已生效通知", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_notifications(
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    now = datetime.now()

    # 只刪除「已經到達時間」的通知
    # 邏輯：(日期 < 今天) OR (日期 == 今天 且 時間 <= 現在)
    db.query(Notification).filter(
        Notification.user_id == current_user.user_id,
        or_(
            Notification.reminder_date_start < now.date(),
            and_(
                Notification.reminder_date_start == now.date(),
                Notification.reminder_time <= now.time()
            )
        )
    ).delete(synchronize_session=False)

    db.commit()
    return None


@router.delete(
    "/{reminder_id}", summary="刪除提醒", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    # 使用 filter 直接 delete 效率較高
    result = (
        db.query(Notification)
        .filter(
            Notification.reminder_id == reminder_id,
            Notification.user_id == current_user.user_id,
        )
        .delete(synchronize_session=False)
    )

    if not result:
        raise HTTPException(status_code=404, detail="提醒不存在或無權限刪除")

    db.commit()
    return None
