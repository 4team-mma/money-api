from fastapi import APIRouter
from web_app.routes.gamification import checkin, missions, cards, summary

router = APIRouter()

# 將子模組掛載進來，並給予更細的分層 prefix
router.include_router(checkin.router, prefix="/checkin")
router.include_router(missions.router, prefix="/missions")
router.include_router(cards.router, prefix="/cards")
router.include_router(summary.router, prefix="/summary")