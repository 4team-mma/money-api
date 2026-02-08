from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from ..database import get_db
from ..models import (
    AddRecord,
    CpiData,
    SalaryBenchmark,
    Member,
)  # 💡 必須匯入 Member 才能查詢使用者職業
from ..dependencies import get_current_user

router = APIRouter()

# 💡 政府資料庫全名橋接表：確保能精準匹配資料庫中的 1 萬多筆資料
GOV_NAME_BRIDGE = {
    "食物類": "一.食物類(指數基期：民國110年=100)",
    "衣著類": "二.衣著類(指數基期：民國110年=100)",
    "居住類": "三.居住類(指數基期：民國110年=100)",
    "交通及通訊類": "四.交通及通訊類(指數基期：民國110年=100)",
    "醫藥保健類": "五.醫藥保健類(指數基期：民國110年=100)",
    "教養娛樂類": "六.教養娛樂類(指數基期：民國110年=100)",
    "雜項類": "七.雜項類(指數基期：民國110年=100)",
    "總指數": "總指數(指數基期：民國110年=100)",
}

# 類別映射表：將使用者輸入的記帳項目對應到簡化大類別
CATEGORY_MAPPING = {
    # --- 食物類 ---
    "飲食": "食物類",
    "早餐": "食物類",
    "午餐": "食物類",
    "超商": "食物類",
    "飲料": "食物類",
    # --- 衣著類 ---
    "衣服": "衣著類",
    "穿著": "衣著類",
    "服飾": "衣著類",
    "登山": "衣著類",
    # --- 居住類 ---
    "居家": "居住類",
    "房租": "居住類",
    "水電瓦斯": "居住類",
    "購物": "居住類",
    "日常用品": "居住類",
    "美容美髮": "居住類",
    # --- 交通及通訊類 ---
    "交通": "交通及通訊類",
    "汽車": "交通及通訊類",
    "機車": "交通及通訊類",
    "加油": "交通及通訊類",
    "電話網路": "交通及通訊類",
    "手機app": "交通及通訊類",
    "電子產品": "交通及通訊類",
    "電腦相關": "交通及通訊類",
    # --- 醫藥保健類 ---
    "醫療保健": "醫藥保健類",
    "醫療": "醫藥保健類",
    "保險": "醫藥保健類",
    "保健食品": "醫藥保健類",
    "保健": "醫藥保健類",
    # --- 教養娛樂類 ---
    "娛樂": "教養娛樂類",
    "社交": "教養娛樂類",
    "遊戲": "教養娛樂類",
    "旅遊": "教養娛樂類",
    "紀念品": "教養娛樂類",
    "機票": "教養娛樂類",
    "聖誕禮物": "教養娛樂類",
    "學習深造": "教養娛樂類",
    "交際應酬": "教養娛樂類",
    "運動": "教養娛樂類",
    "教育": "教養娛樂類",
    "書籍": "教養娛樂類",
    # --- 其他對應 ---
    "其他": "雜項類",  # 收入類別通常不參與 CPI 支出比對
    "繳稅": "雜項類",
    "稅金": "雜項類",
    "罰單": "雜項類",
    "轉帳手續費": "雜項類",
    "奉獻": "雜項類",
    # --- 收入 ---
    "工資": "收入",  # 收入類別通常不參與 CPI 支出比對
    "獎金": "收入",
    "薪資": "收入",
}


# --- 1. 消費 CPI 支出比對路由 ---
@router.get("/cpi-comparison", summary="📊 個人支出與 CPI 指數比對")
def get_cpi_comparison(
    year: str = Query(..., description="年份 (YYYY)", examples=["2025"]),
    month: str = Query(..., description="月份 (MM)", examples=["12"]),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """
    將使用者的當月支出按類別分類，並與政府公布的 **CPI (消費者物價指數) 年增率** 進行比對。

    - **比對邏輯**: 
        - 系統自動將您的記帳標籤（如：午餐、房租）對應到政府的七大類別。
        - **年增率**: 顯示政府資料庫中該類別物價較去年同期漲幅。
    - **自動補償**: 
        - 若該月政府尚未公布資料，系統會自動回溯並參考上個月的趨勢。
    """
    # 1. 驗證輸入參數 (業務邏輯錯誤攔截)
    if not (year.isdigit() and month.isdigit()):
        raise HTTPException(status_code=400, detail="年份或月份格式錯誤")

    target_date = f"{year}-{month.zfill(2)}"

    # 步驟 1: 撈取使用者當月花費
    user_expenses = (
        db.query(AddRecord.add_class, func.sum(AddRecord.add_amount).label("total"))
        .filter(
            AddRecord.user_id == current_user.user_id,
            AddRecord.add_type == 0,
            func.date_format(AddRecord.add_date, "%Y-%m") == target_date,
        )
        .group_by(AddRecord.add_class)
        .all()
    )

    # 步驟 2: 轉換為「簡化大類別」總計
    my_category_totals = {
        CATEGORY_MAPPING.get(record.add_class, "雜項類"): record.total
        for record in user_expenses
    }

    # 步驟 3: 撈取 CPI 資料 (年增率)
    def query_cpi(y, m):
        period_str = f"{y}M{str(m).zfill(2)}"
        # 💡 注意：資料庫中的 data_type 為 "年增率(%)"
        return (
            db.query(CpiData)
            .filter(CpiData.period == period_str, CpiData.data_type == "年增率(%)")
            .all()
        )

    gov_cpi = query_cpi(year, month)
    is_fallback = False
    data_source_note = "✅ 本月 CPI 數據"

    # 2. 自動回溯邏輯：移除 try-except，讓全域處理器處理非預期錯誤 (如 DB 斷線)
    if not gov_cpi:
        current_date = datetime(int(year), int(month), 1)
        prev_date = current_date - timedelta(days=1)
        prev_year, prev_month = str(prev_date.year), str(prev_date.month)
        gov_cpi = query_cpi(prev_year, prev_month)
        if gov_cpi:
            is_fallback = True
            data_source_note = f"ℹ️ 參考上月趨勢 ({prev_year}/{prev_month})"
        else:
            # 這裡不拋出 404，因為「沒有 CPI 數據」對前端來說是可顯示的狀態
            data_source_note = "⚠️ 尚無相關 CPI 資料"

    # 建立政府資料 Map
    gov_data_map = {item.category: float(item.val) for item in gov_cpi}

    # 步驟 4: 組合結果 (自動橋接全名與短名)
    result = []
    for ui_cat, my_total in my_category_totals.items():
        # 透過橋接表拿到資料庫全名，確保 JOIN 成功
        full_db_name = GOV_NAME_BRIDGE.get(ui_cat)
        gov_rate = gov_data_map.get(full_db_name, 0) if full_db_name else 0

        result.append(
            {
                "category": ui_cat,
                "my_spending": float(my_total),
                "gov_cpi_rate": gov_rate,
                "is_fallback": is_fallback,
                "note": data_source_note,
            }
        )

    return result


# --- 2. 薪資比對路由 ---
@router.get("/salary-comparison", summary="💰 個人薪資與行業基準比對")
def get_salary_comparison(
    year: str = Query(..., description="年份", examples=["2025"]),
    month: str = Query(..., description="月份", examples=["12"]),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """
    根據使用者的**職業類型**，比對其收入與政府調查的同行業「平均薪資」。

    - **比對基準**:
        - **名目薪資**: 包含經常性薪資與獎金。
        - **自動匹配**: 根據您個人資料中設定的 `job` 欄位進行匹配（預設為製造業）。
    """
    # 1. 取得使用者職業
    user = db.query(Member).filter(Member.user_id == current_user.user_id).first()
    user_job = user.job if user and user.job else "製造業"

    # 2. 撈取使用者當月總收入
    target_date = f"{year}-{month.zfill(2)}"
    user_income = (
        db.query(func.sum(AddRecord.add_amount))
        .filter(
            AddRecord.user_id == current_user.user_id,
            AddRecord.add_type == 1,
            func.date_format(AddRecord.add_date, "%Y-%m") == target_date,
        )
        .scalar()
        or 0
    )

    # 3. 撈取政府薪資基準
    period_str = f"{year}M{month.zfill(2)}"
    benchmarks = (
        db.query(SalaryBenchmark)
        .filter(
            SalaryBenchmark.industry == user_job,
            SalaryBenchmark.period == period_str,
            SalaryBenchmark.salary_is_real == 0,
        )
        .all()
    )

    # 備案邏輯：找最近的一個月
    if not benchmarks:
        latest = (
            db.query(SalaryBenchmark.period)
            .order_by(SalaryBenchmark.period.desc())
            .first()
        )
        if latest:
            benchmarks = (
                db.query(SalaryBenchmark)
                .filter(
                    SalaryBenchmark.industry == user_job,
                    SalaryBenchmark.period == latest[0],
                    SalaryBenchmark.salary_is_real == 0,
                )
                .all()
            )

    return {
        "user_job": user_job,
        "user_income": float(user_income),
        "period": benchmarks[0].period if benchmarks else period_str,
        "benchmarks": [
            {"type": b.salary_type, "value": float(b.salary_val)} for b in benchmarks
        ],
    }


# --- 3. 實質薪資趨勢路由 (供 Vue 圖表使用) ---
@router.get("/real-salary-trend", summary="📈 實質薪資變動趨勢")
def get_real_salary_trend(
    industry: str = Query(..., description="行業別", examples=["資訊傳輸業"]), 
    db: Session = Depends(get_db)
):
    """
    計算並回傳過去 12 個月的實質薪資趨勢圖表資料。

    - **計算公式**: 
        - $實質薪資 = (名目薪資 / CPI 總指數) \times 100$
    - **意義**: 剔除通膨因素後的真實購買力變化。
    - **回傳**: 包含「名目薪資」與「實質薪資」的對照清單。
    """
    total_index_full_name = GOV_NAME_BRIDGE["總指數"]

    # 關聯查詢兩張表
    results = (
        db.query(
            SalaryBenchmark.period,
            SalaryBenchmark.salary_val.label("nominal"),
            CpiData.val.label("cpi"),
        )
        .join(CpiData, SalaryBenchmark.period == CpiData.period)
        .filter(
            SalaryBenchmark.industry == industry,
            SalaryBenchmark.salary_type == "總薪資",
            CpiData.category == total_index_full_name,
            CpiData.data_type == "原始值",
        )
        .order_by(SalaryBenchmark.period.desc())
        .limit(12)
        .all()
    )

    chart_data = []
    for r in results:
        real_val = (float(r.nominal) / float(r.cpi)) * 100
        chart_data.append(
            {
                "period": r.period,
                "nominal_salary": float(r.nominal),
                "real_salary": round(real_val, 2),
            }
        )

    return chart_data[::-1]  # 回傳正序資料供前端繪圖
