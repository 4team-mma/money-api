# web_app/services/advisor_tools.py
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from ..models.models import Member
from ..routes.stats.expenses import get_expense_category_stats, GroupField
from ..routes.stats.trends import get_net_worth_history

class FinancialAdvisorService:
    @staticmethod
    async def get_ai_context(db: Session, user: Member):
        # 設定時間範圍
        today = date.today()
        this_month_start = today.replace(day=1)
        last_month_start = this_month_start - relativedelta(months=1)
        last_month_end = this_month_start - timedelta(days=1)

        # 1. 抓取支出數據 (調用你原本的 expenses.py 邏輯)
        current_exp = await get_expense_category_stats(this_month_start, today, GroupField.category, db, user)
        past_exp = await get_expense_category_stats(last_month_start, last_month_end, GroupField.category, db, user)

        # 2. 核心演算法：消費基準線 (15% 偵測)
        total_cur = sum(item['amount'] for item in current_exp)
        total_past = sum(item['amount'] for item in past_exp)
        growth_rate = (total_cur - total_past) / total_past if total_past > 0 else 0
        
        # 3. 抓取淨資產 (調用你原本的 trends.py 邏輯)
        net_worth_data = get_net_worth_history(db, user)
        current_net_worth = net_worth_data['monthly'][0]['net'] if net_worth_data['monthly'] else 0

        # 封裝成 JSON，這就是 AI 的「眼睛」
        return {
            "user_profile": {"name": user.name, "job": user.job},
            "metrics": {
                "total_expense": total_cur,
                "growth_from_last_month": f"{growth_rate:.1%}",
                "is_anomaly": growth_rate > 0.15,
                "current_net_worth": current_net_worth
            },
            "top_categories": current_exp[:3] # 只給前三名，避免 AI 混淆
        }