from sqlalchemy.orm import Session
from ..models import Member, Account, AddRecord, CpiData, SalaryBenchmark
from datetime import datetime

class AnythingService:
    @staticmethod
    def get_structured_financial_context(db: Session, user_id: int):
        # 抓取所有支出紀錄
        records = db.query(AddRecord).filter(
            AddRecord.user_id == user_id,
            AddRecord.add_type == "支出"
        ).order_by(AddRecord.add_date.desc()).all()

        # 語言與人格指令強制注入
        lang_instruction = "【系統規範】：以下資料請務必使用『正體中文』進行分析，絕對禁止使用簡體字喵！\n\n"

        if not records:
            return lang_instruction + "目前沒有任何支出紀錄喵。"

        # 將數據轉換為結構化清單，讓 AI 易於統計
        context = lang_instruction + "【官方財務明細清單（精確數據）】\n"
        total_all = 0
        for r in records:
            # 確保日期轉換正確
            date_str = r.add_date.strftime("%Y-%m-%d") if hasattr(r.add_date, 'strftime') else str(r.add_date)
            
            # 修正：項目名稱應讀取 add_title，分類讀取 add_class (根據你 AIService 的邏輯)
            title = getattr(r, 'add_title', '未命名項目')
            category = getattr(r, 'add_class', '一般支出')
            
            context += f"- 日期:{date_str} | 項目:{title} | 金額:{float(r.add_amount)}元 | 分類:{category}\n"
            total_all += float(r.add_amount)
        
        context += f"\n【系統統計總額】: {total_all} 元"
        context += "\n請根據上述清單回答用戶問題，並保持專業理財導師喵喵的人格喵！"
        
        return context