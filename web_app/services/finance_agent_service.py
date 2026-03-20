# web_app/services/finance_agent_service.py
from sqlalchemy.orm import Session
from sqlalchemy import desc
from .finance_tools import FinanceTools
from ..models import CpiData, Member
import re
from datetime import datetime
import pytz
import os

# 🌟 引入所有需要的模板 (包含新增的 KNOWLEDGE_TEMPLATE)
from ..prompts.system_prompts import (
    PERSONAS, BASE_RULES, CHAT_TEMPLATE, 
    ADVISOR_TEMPLATE, RECORD_TEMPLATE, 
    QUERY_TEMPLATE, KNOWLEDGE_TEMPLATE
)
from ..models import CpiData

# 🌟 引入 LangChain 與 Groq 需要的套件
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from ..schemas.bot_schema import RecordResponseSchema


class FinanceAgentService:
    
    @staticmethod
    def analyze_intent(message: str) -> str:
        
        # 🛡️ 1. 擷取真正的「最新發言」，把歷史記憶切掉，避免關鍵字誤判！
        latest_msg = message
        if "【現在】" in message and "小主人說：" in message:
            latest_msg = message.split("小主人說：")[-1]
        elif "]" in message:
            latest_msg = message.split("]")[-1]
            
        # 🛡️ 2. 清理系統指令 (🚨 這裡的 message 要換成 latest_msg ！)
        clean_msg = re.sub(r'\[系統指令.*?\]', '', latest_msg)
        msg = clean_msg.lower()
        
        # 🚨 第零道防線：理財顧問分析
        advisor_keywords = ["健檢", "建議", "理財顧問", "檢視", "診斷", "投資建議", "消費基準"]
        if any(k in msg for k in advisor_keywords):
            return "ADVISOR"
            
        # 🌟 🚨 優先防線：系統知識與手冊 
        # (⚠️ 已經拿掉危險的 "系統" 關鍵字，避免被前端指令誤導)
        knowledge_keywords = ["怎麼用", "設定", "成就", "解鎖", "規則", "什麼是", "卡牌", "等級", "怎麼", "如何", "手冊"]
        if any(k in msg for k in knowledge_keywords):
            return "KNOWLEDGE"
        
        # 🚨 第一道防線：防幻覺！看到疑問詞，強制進入查詢模式
        strict_query = ["多少", "剩下多少","總共", "統計", "分析", "餘額", "明細"]
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
    #  1. 加上 async，並把 user_id: int 改成 user: Member
    async def get_context(db: Session, user: Member, message: str, persona_key: str | None = "cute") -> dict:
        
        user_id = user.user_id # 2.把 user_id 抽出來，讓下面原本的程式碼不會壞掉
        
        intent = FinanceAgentService.analyze_intent(message)
        tw_tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(tw_tz)
        today = now.strftime('%Y-%m-%d %H:%M:%S')
        
        # 3. 解決型別報錯：如果前端沒傳 (None)，就預設給 cute
        safe_persona_key = persona_key if persona_key else "cute"
        current_persona = PERSONAS.get(safe_persona_key, PERSONAS["cute"])
        
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
            # 🌟 名字要對齊你的檔案！
            from .advisor_tools import FinancialAdvisorService
            
            abnormal_report = await FinancialAdvisorService.get_ai_context(db, user) 
            
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

            # 🌟 動態注入防呆字串
            parser = PydanticOutputParser(pydantic_object=RecordResponseSchema)
            prompt = RECORD_TEMPLATE.format(
                today=today,
                persona=current_persona,
                default_acc_name=default_acc_name,
                format_instructions=parser.get_format_instructions() 
            )
            return {"intent": "RECORD", "system_prompt": prompt}

        # ==========================================
        # 💡 意圖 D：系統手冊 (KNOWLEDGE) 🌟 新增
        # ==========================================
        elif intent == "KNOWLEDGE":
            from .vector_db_tools import VectorDBTools
            retrieved_docs = VectorDBTools.search_manual(message)
            prompt = KNOWLEDGE_TEMPLATE.format(
                today=today, 
                persona=current_persona, 
                rules=BASE_RULES, 
                retrieved_docs=retrieved_docs
            )
            return {"intent": "KNOWLEDGE", "system_prompt": prompt}

        # ==========================================
        # 💡 意圖 E：查帳與數據查詢 (QUERY)
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
            
            instruction_rule = "請進行詳細財務分析，可使用數據說明。" if "分析" in msg else "嚴禁廢話與表格，限制在 2-20 中文字內。若問吃什麼，請優先從飲食類別的 add_note 找具體食物，直接回答如：小主人，你吃了包子喵！不准廢話，直接回答重點！嚴禁使用泰文或其他外國語言。"
            
            prompt = QUERY_TEMPLATE.format(
                full_context=full_context,
                persona=current_persona,
                rules=BASE_RULES,
                instruction_rule=instruction_rule
            )
            return {"intent": "QUERY", "system_prompt": prompt}

    # =========================================================
    # 🚀 這是新增的！讓 API Router 呼叫的「強制輸出 JSON」執行器
    # =========================================================
    @staticmethod
    def execute_record_chain(system_prompt: str, user_message: str) -> dict:
        from pydantic import SecretStr
        from langchain_core.output_parsers import PydanticOutputParser
        from ..schemas.bot_schema import RecordResponseSchema
        
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            raise ValueError("找不到 GROQ_API_KEY，請確認 .env 檔案設定喵！")
            
        secure_api_key = SecretStr(groq_api_key)
        
        # 🌟 這裡！把模型換成更聰明的 llama3-70b-8192
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0, api_key=secure_api_key)
        
        parser = PydanticOutputParser(pydantic_object=RecordResponseSchema)
        
        final_prompt = PromptTemplate(
            template="{system_prompt}\n\n[小主人的話]：{user_message}",
            input_variables=["system_prompt", "user_message"]
        )
        
        chain = final_prompt | llm | parser
        result = chain.invoke({"system_prompt": system_prompt, "user_message": user_message})
        
        return result.model_dump()