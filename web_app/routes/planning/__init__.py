from fastapi import APIRouter
from .budgets import router as budgets_router
from .goals import router as goals_router


router = APIRouter()

# 將子模組掛載進來，並給予更細的分層 prefix
router.include_router(budgets_router, prefix="/budgets")

router.include_router(goals_router, prefix="/savings-goals")