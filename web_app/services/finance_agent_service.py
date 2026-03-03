# web_app/services/finance_agent_service.py
from sqlalchemy.orm import Session
from sqlalchemy import desc
from .finance_tools import FinanceTools
from datetime import date
from ..models import CpiData
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
            
        # B. 詢問收支、花費、統計、薪水 (⚡️ 已更新：加入收入相關關鍵字)
        # 這裡補上了：工資, 薪水, 薪資, 賺, 領錢, 獎金, 股息, 利息
        expense_keywords = [
            "花", "支出", "收入", "統計", "分析", "占比", "吃飯", "交通", "買了",
            "工資", "薪水", "薪資", "賺", "領錢", "獎金", "股息", "利息"
        ]
        
        if any(k in msg for k in expense_keywords):
            context_parts.append(FinanceTools.get_monthly_stats(db, user_id))
            context_parts.append(FinanceTools.get_expense_analysis(db, user_id, days=30))
            # 補上最近明細 (這就是讓 AI 看到你 18000 工資的關鍵)
            context_parts.append(FinanceTools.get_recent_transactions(db, user_id, limit=8))

        #  C. 詢問物價 (準確度優化核心)
        if any(k in msg for k in ["物價", "漲價", "通膨", "cpi", "貴", "嚴重", "指標"]):
            # 抓取原始數據字串
            cpi_raw_data = FinanceTools.get_cpi_insight(db, user_id)
            context_parts.append(cpi_raw_data)
            
            # 🚀 主動找出漲幅最高的類別，直接告訴 AI 答案
            latest_cpi = db.query(CpiData).order_by(desc(CpiData.period), desc(CpiData.val)).first()
            if latest_cpi:
                context_parts.append(f"[關鍵洞察]: 目前 CPI 漲幅最高的是「{latest_cpi.category}」，漲幅達 {latest_cpi.val}%。")

        # D. 詢問提醒、繳費
        if any(k in msg for k in ["提醒", "繳費", "行事曆", "忘記"]):
            context_parts.append(FinanceTools.get_upcoming_reminders(db, user_id))

        # E. 預設：如果什麼都沒對到，給基礎背景 (避免 AI 瞎掰)
        if len(context_parts) <= 1:
            context_parts.append(FinanceTools.get_account_summary(db, user_id))
            context_parts.append(FinanceTools.get_monthly_stats(db, user_id))

        # 🚀 新增：動態指令判斷邏輯 (完全取代前端的 smartInstruction)
        instruction_rule = ""
        if "分析" in msg:
            instruction_rule = "請進行詳細財務分析，可使用數據說明。"
        else:
            instruction_rule = "嚴禁廢話與表格，限制在 2-20 中文字內。若問吃什麼，請優先從飲食類別的 add_note 找具體食物(如：包子、拉麵)，直接回答如：小主人，你吃了包子喵！"
        
        # 3. 組合 Prompt
        full_context = "\n\n".join(context_parts)
        
        return f"""
[真實財務資料 (請依此回答)]
{full_context}

[回答規範]
1. 嚴禁編造數據，若資料不在清單上，請直說「喵喵找不到這筆資料」。
2. 保持「理財助手喵喵」的人設，說話可愛，結尾帶「喵~」。
3. {instruction_rule}
4. ⚠️ 系統目前只提供「最近 30 天」與「當月」的資料。若小主人詢問「上個月」、「1月」或更早以前的明確月份，請絕對不要瞎掰數字，直接回答：「喵喵手邊目前只有最近一個月的帳本，其他月份要麻煩小主人看行事曆喵～」
"""