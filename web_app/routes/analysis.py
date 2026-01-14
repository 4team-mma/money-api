from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from ..database import get_db
from ..models import AddRecord, CpiData
from ..dependencies import get_current_user_id

router = APIRouter()

# 1. 定義映射表
CATEGORY_MAPPING = {
    # === 食物類 ===
    "早餐": "食物類",
    "午餐": "食物類",
    "晚餐": "食物類",
    "飲料": "食物類",
    "超市": "食物類",
    "聚餐": "食物類",

    # === 交通類 ===
    "加油": "交通及通訊類",
    "捷運": "交通及通訊類",
    "公車": "交通及通訊類",
    "保養": "交通及通訊類",
    "停車費": "交通及通訊類",

    # === 居住類 ===
    "房租": "居住類",
    "水電費": "居住類",
    "網路費": "居住類",
    
    # ... 其他類別 ...
}

@router.get("/cpi-comparison")
def get_cpi_comparison(
    year: str,   # 前端傳來的查詢年份 (例如 2026)
    month: str,  # 前端傳來的查詢月份 (例如 1)
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    # --- 步驟 1: 撈取使用者的花費 (保持不變) ---
    # 這裡一定要查「當月」的，因為使用者想知道自己「現在」花多少
    # 注意：month 如果是單位數 (1-9)，建議補 0 變成 "01"
    target_date = f"{year}-{month.zfill(2)}" 
    
    user_expenses = db.query(
        AddRecord.add_class,
        func.sum(AddRecord.add_amount).label("total")
    ).filter(
        AddRecord.user_id == user_id,
        func.date_format(AddRecord.add_date, '%Y-%m') == target_date
    ).group_by(AddRecord.add_class).all()

    # --- 步驟 2: Mapping 轉換 (保持不變) ---
    my_category_totals = {}
    for record in user_expenses:
        my_class = record.add_class
        amount = record.total
        big_category = CATEGORY_MAPPING.get(my_class, "其他") # 記得確認 CATEGORY_MAPPING 有定義
        
        if big_category not in my_category_totals:
            my_category_totals[big_category] = 0
        my_category_totals[big_category] += amount

    # --- 🔥 步驟 3 (核心修改): 撈取 CPI 資料，如果沒有就找上個月 ---
    
    # 定義一個內部函式來查資料
    def query_cpi(y, m):
        period_str = f"{y}M{str(m).zfill(2)}" # 格式: 2026M01
        return db.query(CpiData).filter(
            CpiData.period == period_str,
            CpiData.data_type == "年增率"
        ).all()

    # 1. 先試著查「當月」
    gov_cpi = query_cpi(year, month)
    data_source_note = "本月數據" # 標記用

    # 2. 如果當月沒資料 (空陣列)，就去查「上個月」
    if not gov_cpi:
        # 計算上個月
        try:
            current_date = datetime(int(year), int(month), 1)
            # 減去一天回到上個月，再抓該月的年/月
            prev_date = current_date - timedelta(days=1)
            prev_year = str(prev_date.year)
            prev_month = str(prev_date.month)
            
            print(f"⚠️ {year}M{month} 無 CPI 資料，改抓上個月: {prev_year}M{prev_month}")
            
            gov_cpi = query_cpi(prev_year, prev_month)
            data_source_note = f"參考資料 ({prev_year}/{prev_month})"
            
        except Exception as e:
            print(f"日期計算錯誤: {e}")

    # 轉成字典: {'食物類': 3.52, ...}
    gov_data_map = {item.category: float(item.val) for item in gov_cpi}

    # --- 步驟 4: 組合回傳結果 (新增 note 欄位讓前端知道) ---
    result = []
    
    # 如果使用者完全沒花費，也至少要回傳 CPI 資訊 (可選)
    # 這裡示範只回傳有花費的類別
    for category, my_total in my_category_totals.items():
        result.append({
            "category": category,
            "my_spending": my_total,
            "gov_cpi_rate": gov_data_map.get(category, 0),
            "note": data_source_note # 👈 讓前端知道這是最新的還是舊的
        })

    return result