# web_app/services/finance_agent_service.py
from sqlalchemy.orm import Session
from .finance_tools import FinanceTools
from datetime import date

class FinanceAgentService:
    @staticmethod
    def get_context(db: Session, user_id: int, message: str) -> str:
        """
        篩選器核心：根據使用者的訊息內容，智能決定要抓取哪些資料。
        """
        context_parts = []
        msg = message.lower()
        
        # 1. 總是需要的基本資訊
        today = date.today()
        context_parts.append(f"[系統時間]: {today.strftime('%Y-%m-%d')}")

        # 2. 意圖判斷與資料抓取
        
        # A. 詢問資產、餘額、銀行
        if any(k in msg for k in ["錢", "資產", "餘額", "銀行", "存款", "台新", "錢包", "多少"]):
            context_parts.append(FinanceTools.get_account_summary(db, user_id))
            
        # B. 詢問收支、花費、統計
        if any(k in msg for k in ["花", "支出", "收入", "統計", "分析", "占比", "吃飯", "交通", "買了"]):
            context_parts.append(FinanceTools.get_monthly_stats(db, user_id))
            context_parts.append(FinanceTools.get_expense_analysis(db, user_id, days=30))
            # 補上最近明細
            context_parts.append(FinanceTools.get_recent_transactions(db, user_id, limit=8))

        # C. 詢問物價、通膨、CPI
        if any(k in msg for k in ["物價", "漲價", "通膨", "cpi", "貴"]):
            context_parts.append(FinanceTools.get_cpi_insight(db, user_id))

        # D. 詢問提醒、繳費
        if any(k in msg for k in ["提醒", "繳費", "行事曆", "忘記"]):
            context_parts.append(FinanceTools.get_upcoming_reminders(db, user_id))

        # E. 預設：如果什麼都沒對到，給基礎背景
        if len(context_parts) <= 1:
            context_parts.append(FinanceTools.get_account_summary(db, user_id))
            context_parts.append(FinanceTools.get_monthly_stats(db, user_id))

        # 3. 組合 Prompt
        full_context = "\n\n".join(context_parts)
        
        return f"""
[真實財務資料 (請依此回答)]
{full_context}

[回答規範]
1. 嚴禁編造數據，若資料不在清單上，請直說「喵喵找不到這筆資料」。
2. 保持「理財助手喵喵」的人設，說話可愛，結尾帶「喵~」。
"""