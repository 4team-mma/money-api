# 專門處理收入相關的聚合計算。

from fastapi import APIRouter


router = APIRouter()

# 這裡可以先留一個空殼，讓隊友之後寫
@router.get("/category")
async def get_income_category_stats():
    return []