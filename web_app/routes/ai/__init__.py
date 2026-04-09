from fastapi import APIRouter
from .siri_voice import router as voice_router
from .ai_analysis import router as ai_analysis_router
from .line_bot import router as line_bot_router
from .ai_cat_test import router as ai_cat_test_router

router = APIRouter()

# 將子模組掛載進來，並給予更細的分層 prefix
router.include_router(voice_router, prefix="/siri_voice")
router.include_router(ai_analysis_router, prefix="/analysis")
router.include_router(line_bot_router, prefix="/line")
router.include_router(ai_cat_test_router, prefix="/ai_test")
