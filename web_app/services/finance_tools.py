# web_app/services/finance_tools.py
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import date, timedelta
from ..models import Account, AddRecord, Notification, CpiData

# 這裡放入你 analysis.py 裡面的常數，讓工具箱能讀懂類別
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

CATEGORY_MAPPING = {
    "飲食": "食物類", "早餐": "食物類", "午餐": "食物類", "晚餐": "食物類", "飲料": "食物類",
    "交通": "交通及通訊類", "加油": "交通及通訊類", "房租": "居住類", "水電": "居住類",
    "醫療": "醫藥保健類", "娛樂": "教養娛樂類", "旅遊": "教養娛樂類", "衣服": "衣著類"
}

class FinanceTools:
    
    @staticmethod
    def get_account_summary(db: Session, user_id: int) -> str:
        """取得帳戶餘額與總資產"""
        accounts = db.query(Account).filter(Account.user_id == user_id).all()
        if not accounts:
            return "目前沒有設定任何帳戶。"
            
        details = []
        total_assets = 0
        for acc in accounts:
            # 排除不計入資產的項目
            if not acc.exclude_from_assets:
                total_assets += float(acc.current_balance)
            details.append(f"- {acc.account_name}: {float(acc.current_balance):,} 元")
        
        return f"【帳戶資產總覽】\n" + "\n".join(details) + f"\n💰 淨資產總計: {total_assets:,} 元"

    @staticmethod
    def get_monthly_stats(db: Session, user_id: int) -> str:
        """取得本月收支概況"""
        today = date.today()
        this_month_first = today.replace(day=1)
        
        expense = db.query(func.sum(AddRecord.add_amount)).filter(
            AddRecord.user_id == user_id,
            AddRecord.add_type == False,
            AddRecord.add_date >= this_month_first
        ).scalar() or 0
        
        income = db.query(func.sum(AddRecord.add_amount)).filter(
            AddRecord.user_id == user_id,
            AddRecord.add_type == True,
            AddRecord.add_date >= this_month_first
        ).scalar() or 0
        
        net = float(income) - float(expense)
        return f"【本月 ({today.strftime('%Y-%m')}) 概況】\n- 總收入: {float(income):,} 元\n- 總支出: {float(expense):,} 元\n- 淨結餘: {net:,} 元"

    @staticmethod
    def get_expense_analysis(db: Session, user_id: int, days: int = 30) -> str:
        """取得近 30 天支出分類佔比"""
        start_date = date.today() - timedelta(days=days)
        
        results = db.query(
            AddRecord.add_class, 
            func.sum(AddRecord.add_amount).label("total")
        ).filter(
            AddRecord.user_id == user_id,
            AddRecord.add_type == False,
            AddRecord.add_date >= start_date
        ).group_by(AddRecord.add_class).order_by(desc("total")).all()
        
        if not results:
            return "近 30 天沒有支出紀錄。"
            
        total_expense = sum(r.total for r in results)
        summary = f"【近 {days} 天支出分析 (總計 {float(total_expense):,} 元)】\n"
        
        # 取前 5 名
        for r in results[:5]:
            ratio = round((float(r.total) / float(total_expense) * 100), 1)
            summary += f"- {r.add_class}: {float(r.total):,} 元 ({ratio}%)\n"
            
        return summary

    @staticmethod
    def get_cpi_insight(db: Session, user_id: int) -> str:
        """取得 CPI 物價分析"""
        today = date.today()
        # 簡易邏輯：抓上個月的資料來比對
        period_str = f"{today.year}M{str(today.month-1).zfill(2)}" # 例如 2026M01
        if today.month == 1: # 處理跨年
            period_str = f"{today.year-1}M12"

        # 1. 抓使用者的花費類別
        target_date = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        user_expenses = db.query(AddRecord.add_class).filter(
            AddRecord.user_id == user_id,
            AddRecord.add_type == False,
            func.date_format(AddRecord.add_date, "%Y-%m") == target_date
        ).group_by(AddRecord.add_class).all()
        
        user_cats = [r.add_class for r in user_expenses]
        mapped_gov_cats = [GOV_NAME_BRIDGE.get(CATEGORY_MAPPING.get(c, ""), "") for c in user_cats]
        
        # 2. 抓 CPI 年增率
        cpi_data = db.query(CpiData).filter(
            CpiData.period == period_str,
            CpiData.data_type == "年增率(%)",
            CpiData.category.in_(mapped_gov_cats)
        ).all()
        
        if not cpi_data:
            return "目前尚未取得最新的政府 CPI 物價指數資料。"
            
        insight = "【物價指數 (CPI) 觀察】\n"
        for cpi in cpi_data:
            val = float(cpi.val)
            trend = "漲" if val > 0 else "跌"
            short_name = cpi.category.split(".")[1].split("(")[0] if "." in cpi.category else cpi.category
            insight += f"- {short_name}: 年增率 {val}% ({trend})\n"
            
        return insight

    @staticmethod
    def get_upcoming_reminders(db: Session, user_id: int) -> str:
        """取得未來 7 天的提醒"""
        today = date.today()
        end_date = today + timedelta(days=7)
        
        # 修改 filter 條件，只檢查 reminder_date_start 是否在範圍內
        reminders = db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.reminder_date_start >= today,  # 改這裡：大於等於今天
            Notification.reminder_date_start <= end_date # 改這裡：小於等於七天後
        ).order_by(Notification.reminder_date_start.asc()).all()
        
        if not reminders:
            return "未來 7 天沒有設定提醒事項。"
            
        txt = "【未來 7 天提醒事項】\n"
        for r in reminders:
            # 格式化輸出
            txt += f"- {r.reminder_date_start} [{r.reminder_title}]: {r.description or ''}\n"
        return txt

    @staticmethod
    def get_recent_transactions(db: Session, user_id: int, limit: int = 8) -> str:
        """取得最新幾筆收支"""
        records = db.query(AddRecord).filter(
            AddRecord.user_id == user_id
        ).order_by(AddRecord.add_date.desc(), AddRecord.add_id.desc()).limit(limit).all()
        
        if not records:
            return "最近沒有記帳紀錄。"
            
        txt = f"【最近 {limit} 筆收支明細】\n"
        for r in records:
            r_type = "收入" if r.add_type else "支出"
            note = r.add_note if r.add_note else r.add_class
            txt += f"- {r.add_date} | {r_type} | {note} : {float(r.add_amount):,} 元\n"
        return txt