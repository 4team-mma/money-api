from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["使用者管理"])

@router.get("/me")
async def get_me():
    # 未來從 Token 解析出 user_id 後來這裡抓資料
    return {"message": "抓取當前登入者的資料"}

# @router.get("/")
# async def get_users():
#     return {"message": "這是所有使用者清單（僅限管理員）"}

@router.get("/{user_id}")
async def get_user(user_id: int):
    return {"用戶編號": user_id}