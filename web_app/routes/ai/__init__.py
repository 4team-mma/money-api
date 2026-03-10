from fastapi import APIRouter
from .siri_voice import router as voice_router


router = APIRouter()

# 將子模組掛載進來，並給予更細的分層 prefix
router.include_router(voice_router, prefix="/siri_voice")
