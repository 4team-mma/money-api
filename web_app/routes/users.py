from fastapi import APIRouter

router=APIRouter()


@router.get("/me")
async def get_me():
    return{"使用者的什麼?":"要抓什麼?"}

@router.get("/")
async def get_users():
    # 這裡未來會接資料庫查詢
    return {"message": "這是所有使用者清單"}

@router.get("/{user_id}")
async def get_user(user_id:int):
    return {"用戶編號": user_id}


@router.post("/login")
async def login():
    return {"message": "登入成功"}

