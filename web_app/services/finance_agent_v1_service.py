# web_app/services/finance_agent_v1_service.py
import re

class FinanceAgentV1Service:
    """
    這是 MoneyMMA 的元老級大腦 (V1)。
    純粹使用 Regex 與關鍵字過濾，作為 V2 的比對對象與備援。
    """

    @staticmethod
    def analyze_intent(msg: str) -> str:
        # msg 傳進來前已經在 Service 層被轉小寫並清洗過了
        
        # 🚨 第零道防線：理財顧問分析
        advisor_keywords = ["健檢", "建議", "理財顧問", "檢視", "診斷", "投資建議", "消費基準"]
        if any(k in msg for k in advisor_keywords):
            return "ADVISOR"

        # 🌟 🚨 優先防線：系統知識與手冊
        knowledge_keywords = ["怎麼用", "設定", "成就", "解鎖", "規則", "什麼是", "卡牌", "等級", "怎麼", "如何", "手冊"]
        if any(k in msg for k in knowledge_keywords):
            return "KNOWLEDGE"

        # 🚨 第一道核心防線：強化的查詢偵測
        query_trigger = [
            "多少", "剩", "總共", "統計", "分析", "餘額", "明細", "占比", "排行",
            "有沒有", "吃了沒", "買了沒", "過", "紀錄", "查詢", "找一下",
            "答案", "結果", "多少錢", "算了沒" 
        ]
        if any(q in msg for q in query_trigger):
            return "QUERY"

        # 🌟 第一點五道防線 (假設性與評估攔截)
        hypothetical_keywords = ["可以", "夠嗎", "夠不夠", "評估", "能不能", "預算查詢"]
        if any(k in msg for k in hypothetical_keywords):
            return "QUERY"

        # 🚨 第二道防線：記帳與轉帳意圖
        record_keywords = [
            "花", "買", "記帳", "支出", "消費", "吃了", "花了", "付",
            "中獎", "收入", "賺", "薪水", "收",
            "匯", "轉帳", "轉給", "轉到", "轉出", "轉入", "存", "領", "轉"
        ]
        has_number = bool(re.search(r'\d+', msg))
        if any(k in msg for k in record_keywords) and has_number:
            return "RECORD"

        # 🚨 第三道防線：查詢意圖
        query_keywords = ["錢", "資產", "銀行", "存款", "台新", "錢包",
                        "占比", "吃飯", "交通", "工資", "股息", "利息",
                        "物價", "漲價", "通膨", "cpi", "貴", "嚴重", "指標",
                        "提醒", "繳費", "行事曆", "忘記", "預算"]
        if any(k in msg for k in query_keywords):
            return "QUERY"

        return "CHAT"