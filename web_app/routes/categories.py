
# categories.py
# web_app/routes/categories.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import CategoryMapping, Member
# 引入你們原本寫好的權限驗證工具 (請確認路徑是否正確)
from ..dependencies import admin_required, get_current_user 

router = APIRouter()

@router.post("/global", summary="新增全域分類")
def create_global_category(
    user_input: str, 
    dimension: str, 
    db: Session = Depends(get_db),
    # 加入這行：強制要求登入，且驗證是否為 admin
    current_admin: Member = Depends(admin_required) 
):
    # 1. 寫入前先檢查是否已經存在 user_id 為 None (NULL) 且 user_input 相同的資料
    existing_global_cate = db.query(CategoryMapping).filter(
        CategoryMapping.user_id.is_(None),
        CategoryMapping.user_input == user_input
    ).first()

    if existing_global_cate:
        raise HTTPException(status_code=400, detail=f"全域分類 '{user_input}' 已經存在！")

    # 2. 確認沒重複，才執行新增
    new_cate = CategoryMapping(
        user_id=None,
        user_input=user_input,
        dimension=dimension
    )
    db.add(new_cate)
    db.commit()
    db.refresh(new_cate) # 刷新以獲取生成的 cate_id
    
    return {"success": True, "message": "全域分類新增成功", "data": new_cate}