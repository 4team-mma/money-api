from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...database import get_db
from ...models import Setting as SettingModel
from ...schemas import Setting as schemas
# 🌟 引入你的守門員
from ...dependencies import get_current_user 
from ...models import Member

router = APIRouter()

# 1. 獲取當前使用者的設定
@router.get("/me", response_model=schemas.SettingRead)
def get_user_settings(
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user) # 🌟 改用守門員取得 user 物件
):
    """
    獲取當前登入使用者的偏好設定，不需要在 URL 帶 ID。
    """
    user_id = current_user.user_id # 從 Token 解析出來的物件中拿 ID
    
    settings = db.query(SettingModel).filter(SettingModel.user_id == user_id).first()
    
    if not settings:
        # 如果使用者還沒設定過，自動初始化一筆預設資料
        new_settings = SettingModel(user_id=user_id)
        db.add(new_settings)
        db.commit()
        db.refresh(new_settings)
        return new_settings
        
    return settings


# 2. 專門更新主題顏色
@router.patch("/update-theme", response_model=schemas.SettingRead)
def update_app_theme(
    theme_data: schemas.ThemeUpdate, 
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user) # 🌟 守門員
):
    """
    更新主題，自動識別是誰發出的請求
    """
    settings = db.query(SettingModel).filter(SettingModel.user_id == current_user.user_id).first()
    
    if not settings:
        raise HTTPException(status_code=404, detail="找不到設定檔")
    
    settings.app_theme = theme_data.app_theme
    db.commit()
    db.refresh(settings)
    return settings


# 3. 更新所有偏好設定
@router.put("/update-all", response_model=schemas.SettingRead)
def update_all_settings(
    settings_data: schemas.SettingBase, 
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user) # 🌟 守門員
):
    """
    全面更新設定，由 Token 決定對象
    """
    settings = db.query(SettingModel).filter(SettingModel.user_id == current_user.user_id).first()
    
    if not settings:
        raise HTTPException(status_code=404, detail="找不到設定檔")

    # 將 Schema 元素轉換為字典 (排除未設定的欄位)
    update_data = settings_data.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(settings, key, value)

    db.commit()
    db.refresh(settings)
    return settings