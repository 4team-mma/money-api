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
        
        # 1. RECORD (記帳意圖)：有消費動詞，且「包含數字」
        record_keywords = ["花", "買", "記帳", "支出", "消費", "吃了", "花了"]
        has_number = bool(re.search(r'\d+', msg)) 
        if any(k in msg for k in record_keywords) and has_number:
            return "RECORD"
            
        # 2. QUERY (查詢意圖)：詢問財務狀況 (包含你原本設定的所有關鍵字)
        query_keywords = ["錢", "資產", "餘額", "銀行", "存款", "台新", "錢包", "多少", 
                          "統計", "分析", "占比", "吃飯", "交通", "買了", 
                          "工資", "薪水", "薪資", "賺", "領錢", "獎金", "股息", "利息",
                          "物價", "漲價", "通膨", "cpi", "貴", "嚴重", "指標",
                          "提醒", "繳費", "行事曆", "忘記"]
        if any(k in msg for k in query_keywords):
            return "QUERY"
            
        # 3. CHAT (閒聊意圖)：其他通通歸類為閒聊
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
[系統時間]: {today}
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
[系統時間]: {today}
[任務說明]
小主人剛輸入了一筆消費，請擔任專業的財務資料解析員，將文字轉化為結構化的記帳資料。

[分類與提取規則]
1. add_amount (金額): 提取文字中的消費數字。
2. add_class (主類別): 判斷消費所屬的四大預設類別：「飲食」(吃喝相關)、「交通」(加油/搭車)、「居家」(家具/日用品)、「娛樂」(玩樂)。若都不屬於，請根據常理自定義一個大項目名稱(例如: 看病請寫「醫療」)。
3. add_note (備註): 寫入實際消費的具體物品名稱(如: 拉麵、衛生紙)。
4. account_name (扣款帳戶): 預設為「台新銀行」。除非小主人明確提到其他銀行或支付方式(如: 國泰、現金)，才做更改。
5. add_member (成員): 預設為「自己」。除非小主人提到幫別人出錢。
6. add_tag (標籤): 預設為「需要」。若小主人語氣帶有「想要」、「旅遊」，或是提到特定的品牌/地點(如: 麥當勞)，請將這些詞彙用逗號分隔加入(如: "需要,麥當勞")。

[JSON 輸出格式範例] (嚴格遵守，不要回覆其他純文字與Markdown標籤)
{{
    "action": "confirm_record",
    "add_amount": 250,
    "add_class": "飲食",
    "add_note": "拉麵",
    "account_name": "台新銀行",
    "add_member": "自己",
    "add_tag": "需要"
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