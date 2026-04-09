# web_app/services/advisor_tools.py
import numpy as np
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from ..models.models import Member
from ..routes.stats.expenses import get_expense_category_stats, GroupField
from ..routes.stats.trends import get_net_worth_history

class FinancialAdvisorService:
    
    @staticmethod
    def _calculate_z_score_anomaly(current_val: float, history_vals: list, threshold: float = 2.0):
        """內部工具：計算 Z-score 異常"""
        if len(history_vals) < 3:  # 資料量不足以計算標準差時
            return {"is_detected": False, "z_score": 0}
        
        data = np.array(history_vals)
        mean = np.mean(data)
        std = np.std(data)
        
        if std == 0: return {"is_detected": False, "z_score": 0}
        
        z_score = (current_val - mean) / std
        
        # 關鍵修正點：使用 bool() 和 float() 轉換 numpy 型別
        # numpy.bool_ -> bool
        # numpy.float64 -> float
        is_detected = bool(abs(z_score) > threshold)
        z_val = float(z_score)
        
        return {
        "is_detected": is_detected,
        "z_score": round(z_val, 2),
        "severity": "high" if abs(z_val) > 3 else "medium"
        }

    @staticmethod
    async def get_ai_context(db: Session, user: Member):
        # 設定時間範圍
        today = date.today()
        this_month_start = today.replace(day=1)
        
        # 1. 抓取當月數據
        current_exp = await get_expense_category_stats(this_month_start, today, GroupField.category, db, user)
        total_cur = sum(item['amount'] for item in current_exp)

        # 2. 抓取歷史數據 (優化：為了 Z-score，我們需要過去幾個月的總額)
        # 這裡建議未來可以寫一個 function 專門抓「月總額列表」
        # 暫時先用妳原本的 past_exp 計算上個月
        last_month_start = this_month_start - relativedelta(months=1)
        last_month_end = this_month_start - timedelta(days=1)
        past_exp = await get_expense_category_stats(last_month_start, last_month_end, GroupField.category, db, user)
        total_past = sum(item['amount'] for item in past_exp)

        # 3. 執行異常偵測 (目前的歷史資料先用 [total_past] 模擬，建議之後補足過去半年資料)
        # 💡 Julia 這裡可以放妳想測試的假資料列表，例如：[1200, 1300, 1100, 1250]
        history_mock = [1100, 1200, 1150, 1250, 1180] # 模擬過去五個月都很穩定
        anomaly_results = FinancialAdvisorService._calculate_z_score_anomaly(total_cur, history_mock + [total_cur])

        # 4. 抓取淨資產
        net_worth_data = get_net_worth_history(db, user)
        current_net_worth = net_worth_data['monthly'][0]['net'] if net_worth_data['monthly'] else 0

        # 5. 計算增長率
        growth_rate = (total_cur - total_past) / total_past if total_past > 0 else 0

        return {
            "user_profile": {"name": user.name, "job": user.job},
            "metrics": {
                "total_expense": total_cur,
                "growth_from_last_month": f"{growth_rate:.1%}",
                "anomaly_analysis": {
                    "is_anomaly": anomaly_results["is_detected"],
                    "z_score": anomaly_results["z_score"],
                    "severity": anomaly_results["severity"] if anomaly_results["is_detected"] else "low"
                },
                "current_net_worth": current_net_worth
            },
            "top_categories": current_exp[:3]
        }