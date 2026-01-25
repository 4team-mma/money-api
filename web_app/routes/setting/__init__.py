from fastapi import APIRouter
from .setting_export import router as setting_export_router


router = APIRouter()

# 將子模組掛載進來，並給予更細的分層 prefix
router.include_router(setting_export_router, prefix="/setting_export", tags=["報表輸出"])
