# 專門處理時間序列（收支趨勢、淨資產趨勢）的計算，因為趨勢通常是按「月」或「日」分組，邏輯比較接近

from fastapi import APIRouter

router = APIRouter()

# 空殼路徑
@router.get("/cash-flow")
async def get_cash_flow_trend():
    return {}