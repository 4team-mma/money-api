from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from ..models import AddRecord

class AIService:
    @staticmethod
    def get_financial_context(db: Session, user_id: int, user_name: str) -> str:
        """專門負責蒐集使用者的財務上下文"""
        this_month = datetime.now().strftime("%Y-%m")
        
        # 統計支出
        monthly_expense = db.query(func.sum(AddRecord.add_amount)).filter(
            AddRecord.user_id == user_id,
            AddRecord.add_type == 0,
            func.date_format(AddRecord.add_date, "%Y-%m") == this_month
        ).scalar() or 0

        # 這裡未來可以輕鬆增加 CPI 分析、預算提醒等邏輯
        return f"當前使用者是 {user_name}，本月總支出目前為 {float(monthly_expense)} 元喵~"