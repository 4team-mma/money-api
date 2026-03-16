from fastapi import APIRouter
from .siri_voice import router as voice_router
from web_app.routes.ai.ai_analysis import router as ai_analysis_router

router = APIRouter()

# 將子模組掛載進來，並給予更細的分層 prefix
router.include_router(voice_router, prefix="/siri_voice")
router.include_router(ai_analysis_router, prefix="/analysis")
