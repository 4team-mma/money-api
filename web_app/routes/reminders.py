from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def get_reminders():
    return {"message": "帳戶功能開發中"}