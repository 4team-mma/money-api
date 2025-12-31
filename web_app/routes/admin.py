from fastapi import APIRouter

# 調用守門員,並多檢查一項 role == 'admin'。
router = APIRouter()

@router.get("/")
async def admin_index():
    return {"message": "管理後台首頁"}


# 以後可以增加更多管理功能，例如：
# @router.get("/all-users") ...
# @router.delete("/delete-user/{id}") ...