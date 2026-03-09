# web_app/services/finance_agent_service.py
from sqlalchemy.orm import Session
from sqlalchemy import desc
from .finance_tools import FinanceTools
from datetime import date
from ..models import CpiData
import re

class FinanceAgentService:
    
    @staticmethod
    def analyze_intent(message: str) -> str:
        msg = message.lower()
        
        # 🚨 第一道防線：防幻覺！看到疑問詞，強制進入查詢模式
        strict_query = ["多少", "總共", "統計", "分析", "餘額", "明細", "?", "？"]
        if any(q in msg for q in strict_query):
            return "QUERY"
        
        # 🚨 第二道防線：記帳與轉帳意圖 (加入收入與轉帳口語)
        record_keywords = [
            "花", "買", "記帳", "支出", "消費", "吃了", "花了", 
            "中獎", "收入", "賺", "薪水", 
            "匯", "轉帳", "轉給", "轉到", "轉出", "轉入", "存", "領"
        ]
        has_number = bool(re.search(r'\d+', msg)) 
        if any(k in msg for k in record_keywords) and has_number:
            return "RECORD"
            
        # 🚨 第三道防線：原本的查詢意圖
        query_keywords = ["錢", "資產", "銀行", "存款", "台新", "錢包", 
                        "占比", "吃飯", "交通", "工資", "股息", "利息",
                        "物價", "漲價", "通膨", "cpi", "貴", "嚴重", "指標",
                        "提醒", "繳費", "行事曆", "忘記"]
        if any(k in msg for k in query_keywords):
            return "QUERY"
            
        return "CHAT"

    @staticmethod
    def get_context(db: Session, user_id: int, message: str) -> dict:
        intent = FinanceAgentService.analyze_intent(message)
        today = date.today().strftime('%Y-%m-%d')
        
        # ==========================================
        # 💡 意圖 A：純閒聊 / 情緒安撫 (CHAT)
        # ==========================================
        if intent == "CHAT":
            prompt = f"""
[系統時間]: {today}(現在真的是這個時間，不准亂掰！)
[任務說明]
小主人現在只是在跟你聊天。你不需要去查帳本資料！
請扮演貼心、幽默的「理財小助手喵喵」，發揮你的個性跟小主人互動。
[回答規範]
1. 嚴禁給出死板的數據回覆。
2. 說話可愛，結尾帶「喵~」。
3. 嚴禁廢話與表格，限制在 2-20 中文字內。
"""
            return {"intent": "CHAT", "system_prompt": prompt}

        # ==========================================
        # 💡 意圖 B：記帳並要求回傳 JSON (RECORD)
        # ==========================================
        elif intent == "RECORD":
            prompt = f"""
[系統時間]: {today}(現在真的是這個時間，不准亂掰！)
[任務說明]
小主人輸入了財務紀錄。判斷是「支出」、「收入」或「轉帳」，並轉為 JSON。
【極度重要】：只能輸出純 JSON，不可包含 ```json 標籤或任何廢話！

[分類與提取規則]
1. record_type: 花錢填 "expense"；中獎/發薪填 "income"；自己帳戶間資金移動填 "transfer"。
2. add_amount: 提取純數字金額。
3. add_note: 
    - 支出/收入：提取具體項目名稱(如: 拉麵)。
    - 轉帳：除非小主人有明確說理由，否則「add_note」必須固定填寫「一般轉帳」。

【若為 expense 或 income】
- add_class: 支出填「飲食/交通/居家/娛樂」；收入填「薪資/投資/其他收入」。
- account_name: 預設「台新銀行」。
- add_member: 預設「自己」。
- add_tag: 預設「需要」(支出) 或 「意外之財」(收入)。

【若為 transfer】
- from_account: 從哪裡轉出(預設: 台新銀行)。
- to_account: 轉到哪裡去(預設: 一般錢包)。
- add_note: 固定預設為「一般轉帳」(除非小主人有特別提到理由)。

[JSON 輸出範例 - 支出/收入]
{{
    "action": "confirm_record",
    "record_type": "income",
    "add_amount": 400,
    "add_class": "其他收入",
    "add_note": "發票中獎",
    "account_name": "台新銀行",
    "add_member": "自己",
    "add_tag": "意外之財"
}}

[JSON 輸出範例 - 轉帳]
{{
    "action": "confirm_record",
    "record_type": "transfer",
    "add_amount": 1000,
    "add_note": "領生活費",
    "from_account": "台新銀行",
    "to_account": "一般錢包"
}}
"""
            return {"intent": "RECORD", "system_prompt": prompt}

        # ==========================================
        # 💡 意圖 C：查帳與數據分析 (QUERY)
        # ==========================================
        else:
            context_parts = [f"[系統時間]: {today}"]
            msg = message.lower()
            
            # 🚀 完整保留你原本的資料抓取邏輯
            context_parts.append(FinanceTools.get_account_summary(db, user_id))
            context_parts.append(FinanceTools.get_monthly_stats(db, user_id))
            context_parts.append(FinanceTools.get_expense_analysis(db, user_id, days=30))
            context_parts.append(FinanceTools.get_recent_transactions(db, user_id, limit=8))
            
            # CPI 資料抓取 (修復 CpiData 未使用的問題)
            cpi_raw_data = FinanceTools.get_cpi_insight(db, user_id)
            context_parts.append(cpi_raw_data)
            latest_cpi = db.query(CpiData).order_by(desc(CpiData.period), desc(CpiData.val)).first()
            if latest_cpi:
                context_parts.append(f"[關鍵洞察]: 目前 CPI 漲幅最高的是「{latest_cpi.category}」，漲幅達 {latest_cpi.val}%。")
            
            context_parts.append(FinanceTools.get_upcoming_reminders(db, user_id))
            
            full_context = "\n\n".join(context_parts)
            
            # 動態指令保留
            instruction_rule = "請進行詳細財務分析，可使用數據說明。" if "分析" in msg else "嚴禁廢話與表格，限制在 2-20 中文字內。若問吃什麼，請優先從飲食類別的 add_note 找具體食物，直接回答如：小主人，你吃了包子喵！"
            
            prompt = f"""
[真實財務資料 (請依此回答)]
{full_context}

[回答規範]
1. 嚴禁編造數據，若資料不在清單上，請直說「喵喵找不到這筆資料」。
2. 保持「理財助手喵喵」的人設，說話可愛，結尾帶「喵~」。
3. {instruction_rule}
4. ⚠️ 系統目前只提供「最近 30 天」與「當月」的資料。若小主人詢問「上個月」或更早以前的明確月份，請絕對不要瞎掰數字，直接回答：「喵喵手邊目前只有最近一個月的帳本，其他月份要麻煩小主人看行事曆喵～」
"""
            return {"intent": "QUERY", "system_prompt": prompt}