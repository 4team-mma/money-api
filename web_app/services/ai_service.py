from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date
from ..models import Member, Account, AddRecord, CpiData, SalaryBenchmark

class AIService:
    @staticmethod
    def get_full_financial_context(db: Session, user_id: int) -> str:
        # 1. 抓取使用者資訊，確保獲取真實姓名以取代「測試者」
        user = db.query(Member).filter(Member.user_id == user_id).first()
        if not user:
            return "系統找不到使用者，請重新登入喵。"

        user_name = user.name 
        user_job = user.job

        # 2. 抓取今日所有詳細紀錄
        today = date.today()
        today_records = db.query(AddRecord).filter(
            AddRecord.user_id == user_id,
            AddRecord.add_date == today
        ).all()
        
        today_details = ""
        today_sum = 0
        if today_records:
            for r in today_records:
                label = "支出" if r.add_type == 0 else "收入"
                # 關鍵修正：優先讀取備註 add_note (如：食物名稱)
                item_name = r.add_note if r.add_note else "未命名項目"
                tags = f" | 標籤:{r.add_tag}" if r.add_tag else ""
                
                # 強制格式化，讓 AI 易於辨識，避免亂加總
                today_details += f"- 【{label}明細】名稱:{item_name} | 金額:{float(r.add_amount)}元 | 類別:{r.add_class}{tags}\n"
                if r.add_type == 0:
                    today_sum += float(r.add_amount)
        else:
            today_details = "今日尚無紀錄喵。\n"

        # 3. 歷史月份摘要 (透過資料庫加總，解決 1 月份算錯 4865 元的問題)
        history = db.query(
            func.date_format(AddRecord.add_date, "%Y-%m").label("month"),
            func.sum(AddRecord.add_amount).label("total")
        ).filter(AddRecord.user_id == user_id, AddRecord.add_type == 0).group_by("month").all()

        history_text = "\n".join([f"- {h.month}: 支出總計 {float(h.total)}元" for h in history])

        # 4. 強制正體中文與事實鎖定指令集
        return f"""
你是專業理財助手「喵喵」。現在日期是 {today}。
【絕對指令】:
1. 必須使用「正體中文(繁體中文)」回答，禁用簡體字。
2. 說話結尾必帶「喵」。
3. 使用者是「{user_name}」，嚴禁稱呼他為「測試者」。
4. 嚴禁編造數據！若清單中沒有 1200 元的紀錄，絕對不可提到該數字！

【真實數據清單】:
- 今日明細:
{today_details}
- 今日支出統計: {today_sum} 元 (此為唯一正確金額)

【歷史月份參考】:
{history_text if history else "查無歷史數據喵。"}

【任務】: 請根據上述真實數據，分析 {user_name} 的財務狀況。若有標籤為「想要」的項目，請簡短給予節流建議。
"""