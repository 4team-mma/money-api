# web_app/routes/stats/trends.py
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case, text
from datetime import date
import logging
from web_app.database import get_db
from web_app.models.models import AddRecord, Member
from web_app.dependencies import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/cash-flow")
async def get_cash_flow_trend(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    try:
        # 1. 取得使用者 ID
        u_id = current_user.user_id

        # 2. 執行查詢
        # 🌟 關鍵修正：將 case([(條件, 值)], else_=0) 改為 case((條件, 值), else_=0)
        # 也就是拿掉中括號 []，直接傳入元組
        results = db.query(
            AddRecord.add_date.label("row_date"),
            func.sum(case((AddRecord.add_type == True, AddRecord.add_amount), else_=0)).label("income"),
            func.sum(case((AddRecord.add_type == False, AddRecord.add_amount), else_=0)).label("expense")
        ).filter(
            AddRecord.user_id == u_id,
            AddRecord.add_date >= start_date,
            AddRecord.add_date <= end_date
        ).group_by(
            AddRecord.add_date
        ).order_by(
            AddRecord.add_date.asc()
        ).all()

        # 3. 格式化回傳 (將 Decimal 轉為 float 避免 JSON 報錯)
        formatted_data = []
        for r in results:
            formatted_data.append({
                "date": r.row_date.strftime("%Y-%m-%d"),
                "income": float(r.income or 0),
                "expense": float(r.expense or 0),
                "net": float((r.income or 0) - (r.expense or 0))
            })

        return formatted_data

    except Exception as e:
        logger.error(f"趨勢 API 錯誤: {str(e)}")
        # 將具體錯誤傳回前端方便除錯
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/net-worth-history")
def get_net_worth_history(
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    user_id = current_user.user_id
        
    # 1. 取得該使用者的「當前」總資產（用於倒推）
    res_total = db.execute(
        text("SELECT SUM(current_balance) FROM accounts WHERE user_id = :uid"),
        {"uid": user_id}
    ).fetchone()
    current_total = float(res_total[0]) if res_total and res_total[0] is not None else 0.0

    # --- 2. 處理每日資料 (Daily) ---
    query_daily = text("""
        SELECT 
            DATE(add_date) as day_key,
            SUM(CASE WHEN add_type = 1 THEN add_amount ELSE -add_amount END) as net_change
        FROM adds
        WHERE user_id = :uid
        GROUP BY day_key
        ORDER BY day_key DESC
    """)
    daily_changes = db.execute(query_daily, {"uid": user_id}).fetchall()

    daily_results = []
    running_balance_d = current_total
    for row in daily_changes:
        d_key = str(row[0]) 
        change = float(row[1])
        daily_results.append({
            "id": f"d_{d_key}",
            "date": d_key,
            "period": d_key,
            "net": round(running_balance_d, 2),
            "diff": round(change, 2)
        })
        running_balance_d -= change

    # --- 3. 處理月資料 (Monthly) ---
    query_monthly = text("""
        SELECT 
            CONCAT(YEAR(add_date), '-', LPAD(MONTH(add_date), 2, '0')) as month_key,
            SUM(CASE WHEN add_type = 1 THEN add_amount ELSE -add_amount END) as net_change
        FROM adds
        WHERE user_id = :uid
        GROUP BY month_key
        ORDER BY month_key DESC
    """)
    monthly_changes = db.execute(query_monthly, {"uid": user_id}).fetchall()

    monthly_results = []
    running_balance_m = current_total
    for row in monthly_changes:
        m_key = row[0]
        change = float(row[1])
        monthly_results.append({
            "id": f"m_{m_key}",
            "date": f"{m_key}-01",
            "period": f"{m_key.split('-')[0]}年{m_key.split('-')[1]}月",
            "net": round(running_balance_m, 2),
            "diff": round(change, 2)
        })
        running_balance_m -= change

    # --- 4. 處理年資料 (Yearly) ---
    query_yearly = text("""
        SELECT 
            YEAR(add_date) as year_key,
            SUM(CASE WHEN add_type = 1 THEN add_amount ELSE -add_amount END) as net_change
        FROM adds
        WHERE user_id = :uid
        GROUP BY year_key
        ORDER BY year_key DESC
    """)
    yearly_changes = db.execute(query_yearly, {"uid": user_id}).fetchall()

    yearly_results = []
    running_balance_y = current_total
    for row in yearly_changes:
        y_key = str(row[0])
        change = float(row[1])
        yearly_results.append({
            "id": f"y_{y_key}",
            "date": f"{y_key}-01-01",
            "period": f"{y_key}年",
            "net": round(running_balance_y, 2),
            "diff": round(change, 2)
        })
        running_balance_y -= change

    return {
        "daily": daily_results, 
        "monthly": monthly_results, 
        "yearly": yearly_results
    }