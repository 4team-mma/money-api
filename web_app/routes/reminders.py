from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import date
import calendar  # 用於獲取該月最後一天
from ..database import get_db
from ..models import Member, Notification
from ..schemas.notification import (
    NotificationCreate,
    NotificationResponse,
    NotificationUpdate,
)
from ..dependencies import get_current_user

router = APIRouter()


@router.get(
    "/calendar/monthly",
    summary="查詢指定月份的所有提醒",
    response_model=List[NotificationResponse],
)
async def get_monthly_reminders(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """
    查詢提醒區間包含指定月份的所有提醒。
    邏輯：(開始日期 <= 月末) 且 (結束日期 >= 月初)
    """
    # 1. 計算該月的第一天與最後一天
    first_day = date(year, month, 1)
    last_day_num = calendar.monthrange(year, month)[1]
    last_day = date(year, month, last_day_num)

    # 2. 建立查詢
    # 區間重疊邏輯：
    # 提醒開始日期 <= 該月最後一天
    # AND
    # 提醒結束日期 >= 該月第一天
    query = db.query(Notification).filter(
        Notification.user_id == current_user.user_id,
        Notification.reminder_date_start <= last_day,
        Notification.reminder_date_end >= first_day,
    )

    # 3. 排序
    results = query.order_by(
        Notification.reminder_date_start.asc(), Notification.reminder_time.asc()
    ).all()

    # 4. 回傳 (Schema 會自動處理 HH:MM:SS 格式)
    return results


@router.post("/", summary="新增提醒", response_model=NotificationResponse)
async def create_reminder(
    data: NotificationCreate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    # 直接解包資料並寫入
    new_reminder = Notification(user_id=current_user.user_id, **data.model_dump())
    db.add(new_reminder)
    db.commit()
    db.refresh(new_reminder)

    # 💡 提示：若 Schema 有設定 from_attributes=True，可直接回傳 ORM 物件
    # 若欄位名不對應，建議在 Schema 中使用 Alias 或 @computed_field
    return new_reminder


@router.patch("/{reminder_id}", summary="修改提醒", response_model=NotificationResponse)
async def update_reminder(
    reminder_id: int,
    data: NotificationUpdate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    # 1. 業務邏輯：查無資料才手動拋出 404
    db_reminder = (
        db.query(Notification)
        .filter(
            Notification.reminder_id == reminder_id,
            Notification.user_id == current_user.user_id,
        )
        .first()
    )

    if not db_reminder:
        raise HTTPException(status_code=404, detail="找不到該筆提醒")

    # 2. 更新邏輯：由全域處理器監控可能發生的 DB 崩潰
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_reminder, key, value)

    db.commit()
    db.refresh(db_reminder)

    # 3. 回傳：由於 Schema 有了 validation_alias，這裡直接回傳物件，Pydantic 會處理一切
    return db_reminder


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
