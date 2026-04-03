from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...database import get_db
from ...models import Setting as SettingModel
from ...schemas import Setting as schemas
from ...dependencies import get_current_user
from ...models import Member

router = APIRouter()

# 1. 獲取當前使用者的設定
@router.get(
    "/me",
    response_model=schemas.SettingRead,
    summary="🔍 獲取個人偏好設定",
    description="透過 Token 自動識別身份，獲取該使用者的主題顏色、語言等設定。若無設定則自動初始化。"
)
def get_user_settings(
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    user_id = current_user.user_id
    settings = db.query(SettingModel).filter(SettingModel.user_id == user_id).first()

    if not settings:
        new_settings = SettingModel(user_id=user_id)
        db.add(new_settings)
        db.commit()
        db.refresh(new_settings)
        return new_settings

    return settings


# 2. 專門更新主題顏色
@router.patch(
    "/update-theme",
    response_model=schemas.SettingRead,
    summary="🌈 快速更新主題顏色",
    description="僅針對 App 的主題色彩進行局部更新（Patch）。"
)
def update_app_theme(
    theme_data: schemas.ThemeUpdate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    settings = db.query(SettingModel).filter(SettingModel.user_id == current_user.user_id).first()

    if not settings:
        raise HTTPException(status_code=404, detail="找不到設定檔")

    settings.app_theme = theme_data.app_theme
    db.commit()
    db.refresh(settings)
    return settings


# 3. 更新所有偏好設定
@router.put(
    "/update-all",
    response_model=schemas.SettingRead,
    summary="⚙️ 全面更新設定項目",
    description="完整覆蓋使用者的所有偏好設定項目（如語言、通知開關、字體大小等）。"
)
def update_all_settings(
    settings_data: schemas.SettingBase,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    settings = db.query(SettingModel).filter(SettingModel.user_id == current_user.user_id).first()

    if not settings:
        raise HTTPException(status_code=404, detail="找不到設定檔")

    update_data = settings_data.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(settings, key, value)

    db.commit()
    db.refresh(settings)
    return settings
