# web_app/services/finance_agent_service.py
from sqlalchemy.orm import Session
from sqlalchemy import desc
from .finance_tools import FinanceTools
from datetime import date
# 🌟 引入所有需要的模板
from ..prompts.system_prompts import PERSONAS, BASE_RULES, CHAT_TEMPLATE, ADVISOR_TEMPLATE, RECORD_TEMPLATE, QUERY_TEMPLATE
from ..models import CpiData
import re
from datetime import datetime
import pytz

class FinanceAgentService:
    
    @staticmethod
    def analyze_intent(message: str) -> str:
        msg = message.lower()
        
        # 🚨 第零道防線：理財顧問分析
        advisor_keywords = ["健檢", "建議", "理財顧問", "檢視", "診斷", "投資建議", "消費基準"]
        if any(k in msg for k in advisor_keywords):
            return "ADVISOR"
        
        # 🚨 第一道防線：防幻覺！看到疑問詞，強制進入查詢模式
        strict_query = ["多少", "總共", "統計", "分析", "餘額", "明細", "?", "？"]
        if any(q in msg for q in strict_query):
            return "QUERY"
        
        # 🚨 第二道防線：記帳與轉帳意圖
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
        tw_tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(tw_tz)
        today = now.strftime('%Y-%m-%d %H:%M:%S')
        
        # 預設使用可愛喵喵
        current_persona = PERSONAS["cute"]
        
        # ==========================================
        # 💡 意圖 A：純閒聊 / 情緒安撫 (CHAT)
        # ==========================================
        if intent == "CHAT":
            prompt = CHAT_TEMPLATE.format(
                today=today,
                persona=current_persona,
                rules=BASE_RULES
            )
            return {"intent": "CHAT", "system_prompt": prompt}

        # ==========================================
        # 💡 意圖 B：理財顧問與基準線分析 (ADVISOR)
        # ==========================================
        elif intent == "ADVISOR":
            from .advisor_tools import AdvisorTools
            abnormal_report = AdvisorTools.calculate_baseline_and_anomalies(db, user_id)
            
            prompt = ADVISOR_TEMPLATE.format(
                today=today,
                persona=PERSONAS["professional"], # 強制使用專業喵喵
                abnormal_report=abnormal_report
            )
            return {"intent": "ADVISOR", "system_prompt": prompt}
        
        # ==========================================
        # 💡 意圖 C：記帳並要求回傳 JSON (RECORD)
        # ==========================================
        elif intent == "RECORD":
            from ..models import Account
            first_acc = db.query(Account).filter(Account.user_id == user_id).first()
            default_acc_name = first_acc.account_name if first_acc else "我的錢包"

            prompt = RECORD_TEMPLATE.format(
                today=today,
                default_acc_name=default_acc_name
            )
            return {"intent": "RECORD", "system_prompt": prompt}

        # ==========================================
        # 💡 意圖 D：查帳與數據查詢 (QUERY)
        # ==========================================
        else:
            context_parts = [f"[系統時間]: {today}"]
            msg = message.lower()
            
            context_parts.append(FinanceTools.get_account_summary(db, user_id))
            context_parts.append(FinanceTools.get_monthly_stats(db, user_id))
            context_parts.append(FinanceTools.get_expense_analysis(db, user_id, days=30))
            context_parts.append(FinanceTools.get_recent_transactions(db, user_id, limit=8))
            
            cpi_raw_data = FinanceTools.get_cpi_insight(db, user_id)
            context_parts.append(cpi_raw_data)
            latest_cpi = db.query(CpiData).order_by(desc(CpiData.period), desc(CpiData.val)).first()
            if latest_cpi:
                context_parts.append(f"[關鍵洞察]: 目前 CPI 漲幅最高的是「{latest_cpi.category}」，漲幅達 {latest_cpi.val}%。")
            
            context_parts.append(FinanceTools.get_upcoming_reminders(db, user_id))
            
            full_context = "\n\n".join(context_parts)
            
            instruction_rule = "請進行詳細財務分析，可使用數據說明。" if "分析" in msg else "嚴禁廢話與表格，限制在 2-20 中文字內。若問吃什麼，請優先從飲食類別的 add_note 找具體食物，直接回答如：小主人，你吃了包子喵！"
            
            prompt = QUERY_TEMPLATE.format(
                full_context=full_context,
                persona=current_persona,
                rules=BASE_RULES,
                instruction_rule=instruction_rule
            )
            return {"intent": "QUERY", "system_prompt": prompt}