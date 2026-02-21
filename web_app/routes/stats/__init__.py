from fastapi import APIRouter
from .expenses import router as expenses_router
from .income import router as income_router
from .trends import router as trends_router

router = APIRouter()

# 將子模組掛載進來，並給予更細的分層 prefix
router.include_router(expenses_router, prefix="/expenses")
router.include_router(income_router, prefix="/income")
router.include_router(trends_router, prefix="/trends")
