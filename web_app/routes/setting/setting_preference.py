from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...database import get_db
from ...models import Setting as SettingModel  # 為了避免跟 Schema 撞名，加上 Model 字尾
from ...schemas import Setting as schemas      # 引入你的 Setting.py Schema 檔案

router = APIRouter()

# 獲取當前使用者的設定
@router.get("/me", response_model=schemas.SettingRead)
def get_user_settings(user_id: int, db: Session = Depends(get_db)):
    """
    獲取指定使用者的偏好設定，如果不存在則自動建立一筆預設值
    """
    # 這裡的 SettingModel 對應你 models/__init__.py 裡的 Setting 類別
    settings = db.query(SettingModel).filter(SettingModel.user_id == user_id).first()
    
    if not settings:
        # 如果使用者還沒設定過，自動初始化一筆預設資料
        new_settings = SettingModel(user_id=user_id)
        db.add(new_settings)
        db.commit()
        db.refresh(new_settings)
        return new_settings
        
    return settings



# 專門更新前台主題 (對應你 Vue 的 changeTheme)
@router.patch("/update-theme", response_model=schemas.SettingRead)
def update_app_theme(
    theme_data: schemas.ThemeUpdate, 
    user_id: int, 
    db: Session = Depends(get_db)
):
    """
    更新 app_theme 欄位
    """
    settings = db.query(SettingModel).filter(SettingModel.user_id == user_id).first()
    
    if not settings:
        raise HTTPException(status_code=404, detail="找不到設定檔")
    
    settings.app_theme = theme_data.app_theme
    db.commit()
    db.refresh(settings)
    return settings



@router.put("/update-all", response_model=schemas.SettingRead)
def update_all_settings(
    settings_data: schemas.SettingBase, # 👈 這裡成功引入了你的 SettingBase Schema
    user_id: int, 
    db: Session = Depends(get_db)
):
    settings = db.query(SettingModel).filter(SettingModel.user_id == user_id).first()
    
    if not settings:
        raise HTTPException(status_code=404, detail="找不到設定檔")

    # 將 Schema 元素轉換為字典 (排除未設定的欄位)
    update_data = settings_data.model_dump(exclude_unset=True)

    # 這裡就是關鍵：將 Schema 裡的元素一一塞進資料庫 Model
    for key, value in update_data.items():
        setattr(settings, key, value)

    db.commit()
    db.refresh(settings)
    return settings

