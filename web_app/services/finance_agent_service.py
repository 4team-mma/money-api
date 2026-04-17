# web_app/services/finance_agent_service.py
from sqlalchemy.orm import Session
from sqlalchemy import text
from .finance_tools import FinanceTools
from ..models import Member
import re
from datetime import datetime
import pytz
import os

# 🌟 引入所有需要的模板
from ..prompts.system_prompts import (
    PERSONAS, BASE_RULES, CHAT_TEMPLATE,
    ADVISOR_TEMPLATE, RECORD_TEMPLATE,
    KNOWLEDGE_TEMPLATE
)

# 🌟 引入 LangChain 與 Groq 需要的套件
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from ..schemas.bot_schema import RecordResponseSchema
from .finance_agent_mixai_service import FinanceAgentMixAIService

class FinanceAgentService:

    @staticmethod
    def analyze_intent(message: str) -> str:
        # 🛡️ 1. 擷取真正的「最新發言」
        latest_msg = message
        if "【現在】" in message and "小主人說：" in message:
            latest_msg = message.split("小主人說：")[-1]
        elif "]" in message:
            latest_msg = message.split("]")[-1]

        # 🛡️ 2. 清理系統指令
        clean_msg = re.sub(r'\[系統指令.*?\]', '', latest_msg)
        msg = clean_msg.lower()

        # 🚨 第零道防線：理財顧問分析
        advisor_keywords = ["健檢", "建議", "理財顧問", "檢視", "診斷", "投資建議", "消費基準"]
        if any(k in msg for k in advisor_keywords):
            return "ADVISOR"

        # 🌟 🚨 優先防線：系統知識與手冊
        knowledge_keywords = ["怎麼用", "設定", "成就", "解鎖", "規則", "什麼是", "卡牌", "等級", "怎麼", "如何", "手冊"]
        if any(k in msg for k in knowledge_keywords):
            return "KNOWLEDGE"

        # 🚨 第一道核心防線：強化的查詢偵測 (新增了有沒有、過、紀錄)
        # 只要是問事實、問歷史、問有沒有，通通送去 QUERY
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

    


    @staticmethod
    async def get_context(
        db: Session, 
        user: Member, 
        message: str, 
        persona_key: str | None = "cute", 
        override_intent: str | None = None,
        version: str = "v1"  # 加上這一個開關，預設是 v1
        ) -> dict:

        user_id = user.user_id

        # 🛡️ 1. 定義 clean_query
        clean_query = message
        if "小主人說：" in message:
            clean_query = message.split("小主人說：")[-1]
        elif "]" in message:
            clean_query = message.split("]")[-1]
        clean_query = re.sub(r'\[系統指令.*?\]', '', clean_query).strip()
        
        # 🧠 2. 確定大腦版本並取得意圖 (變數 intent 在此正式定義)
        if override_intent:
            intent = override_intent
            confidence = 1.0
        elif version == "v2":
            mix_res = FinanceAgentMixAIService.analyze_intent(message)
            intent = mix_res["final_intent"]
            confidence = mix_res["confidence"]
            print(f"🧠 [V2 大腦啟動] 偵測意圖為: {intent} (信心度: {confidence})")
        else:
            intent = FinanceAgentService.analyze_intent(message)
            confidence = 1.0

        # 🛡️ 3. [新增且修正] 攔截邏輯：解決「閒聊帶錢」與「感性發言」的區隔
        # 理由：只有當意圖是 CHAT，且包含錢的關鍵字，且具有「詢問語氣」時才轉 QUERY
        money_keywords = ["收入", "支出", "多少", "剩", "花費", "總額", "答案"]
        question_marks = ["？", "?", "多少", "幾", "算", "查詢"]
        
        if intent == "CHAT" and any(k in message for k in money_keywords):
            if any(q in message for q in question_marks):
                intent = "QUERY"
                print(f"🛡️ [強制轉換] 偵測到詢問財務問題，轉為 QUERY")
            # 💡 補充：如果只是說「收入好多好開心」，沒有詢問語氣，就會維持 CHAT

        # 🛡️ 4. 質疑攔截
        doubt_keywords = ["為什麼", "怎算的", "算錯", "不對", "為啥", "不是吧"]
        if intent in ["RECORD", "MULTI_RECORD"] and any(k in message for k in doubt_keywords):
            intent = "QUERY"
            print(f"🛡️ [攔截] 偵測到質疑語氣，將 {intent} 強制轉為 QUERY")

        tw_tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(tw_tz)
        today = now.strftime('%Y-%m-%d %H:%M:%S')

        safe_persona_key = persona_key if persona_key else "cute"
        current_persona = PERSONAS.get(safe_persona_key, PERSONAS["cute"])

        # ==========================================
        # 💡 意圖 A：純閒聊 (CHAT)
        # ==========================================
        if intent == "CHAT":
            prompt = CHAT_TEMPLATE.format(
                today=today,
                persona=current_persona,
                rules=BASE_RULES
            )
            # ✅ 補上 confidence
            return {"intent": "CHAT", "system_prompt": prompt, "confidence": confidence}

        # ==========================================
        # 💡 意圖 B：理財顧問 (ADVISOR)
        # ==========================================
        elif intent in ["ADVISOR", "MULTI_ADVISOR"]:
            from .advisor_tools import FinancialAdvisorService
            abnormal_report = await FinancialAdvisorService.get_ai_context(db, user)
            prompt = ADVISOR_TEMPLATE.format(
                today=today,
                persona=PERSONAS["professional"],
                abnormal_report=abnormal_report
            )
            # ✅ 補上 confidence
            return {"intent": intent, "system_prompt": prompt, "confidence": confidence}

        # ==========================================
        # 💡 意圖 C：記帳並要求回傳 JSON (RECORD)
        # ==========================================
        elif intent in ["RECORD", "MULTI_RECORD"]:
            from ..models import Account
            first_acc = db.query(Account).filter(Account.user_id == user_id).first()
            default_acc_name = first_acc.account_name if first_acc else "我的錢包"

            parser = PydanticOutputParser(pydantic_object=RecordResponseSchema)
            prompt = RECORD_TEMPLATE.format(
                today=today,
                persona=current_persona,
                default_acc_name=default_acc_name,
                format_instructions=parser.get_format_instructions()
            )
            # ✅ 補上 confidence
            return {"intent": intent, "system_prompt": prompt, "confidence": confidence}

        # ==========================================
        # 💡 意圖 D：系統手冊 (KNOWLEDGE)
        # ==========================================
        elif intent in ["KNOWLEDGE", "MULTI_KNOWLEDGE"]:
            from .vector_db_tools import VectorDBTools
            retrieved_docs = VectorDBTools.search_manual(clean_query) # 使用乾淨的訊息
            prompt = KNOWLEDGE_TEMPLATE.format(
                today=today,
                persona=current_persona,
                rules=BASE_RULES,
                retrieved_docs=retrieved_docs
            )
            # ✅ 補上 confidence
            return {"intent": intent, "system_prompt": prompt, "confidence": confidence}


        # ==========================================
        # 💡 意圖 E：智能數據查詢 (Text-to-SQL SOP 模式)
        # ==========================================
        elif intent in ["QUERY", "MULTI_QUERY"]:
            # 🚀 1. 初始化權限資訊與背景 (保留原有邏輯)
            db_info = "【📁 帳本權限資訊】: 你擁有從 2026-01-01 至今的所有歷史明細權限。"
            context_parts = [f"[系統時間]: {today}", db_info]

            from .sql_generator_service import SQLGeneratorService
            from ..database import SessionLocal
            sql_data_found = False
            precise_val = 0

            try:
                # 🛡️ 2. 擷取乾淨訊息
                clean_query = message.split("小主人說：")[-1] if "小主人說：" in message else message
                clean_query = re.sub(r'\[系統指令.*?\]', '', clean_query).strip()

                # 🚀 3. 呼叫重構後的 SQL 引擎
                generated_sql = await SQLGeneratorService.generate_sql(clean_query, user_id)
                print(f"🕵️‍♂️ [SQL 引擎啟動]：{generated_sql}")

                if generated_sql and generated_sql.lower().startswith("select"):
                    with SessionLocal() as db_session:
                        result = db_session.execute(text(generated_sql))
                        sql_result = result.fetchall()

                        # 🛡️ 4. 數據處理：強制轉整數並處理 None
                        if sql_result:
                            raw_val = sql_result[0][0] if sql_result[0][0] is not None else 0
                            precise_val = int(round(float(raw_val)))

                            # 🔥 修正：把小主人的問題 (clean_query) 塞進去，不讓 AI 猜測「該項目」是什麼
                            context_parts.append(
                                f"【📊 資料庫精確查詢結果】：\n"
                                f"針對小主人的提問「{clean_query}」，系統查出的精準總金額為：「{precise_val}」元。"
                            )
                            sql_data_found = True
                        else:
                            context_parts.append(f"【⚠️ 查詢結果】: 資料庫搜尋回報，找不到關於「{clean_query}」的紀錄。")
                            sql_data_found = True 
            except Exception as e:
                print(f"❌ SQL 執行報警: {e}")
                context_parts.append(f"【⚠️ 系統異常】: 資料庫連線失敗，請小主人稍後再試。")

            # 🚀 6. 補底參考邏輯 (保留不變)
            if not sql_data_found:
                context_parts.append("【📊 當前帳戶餘額概況】")
                context_parts.append(FinanceTools.get_account_summary(db, user_id))
                context_parts.append("【📅 本月收支參考數據(4月)】")
                context_parts.append(FinanceTools.get_monthly_stats(db, user_id))
            
            # 🌟 組合上下文
            full_context = "\n\n".join(context_parts)

            # 🧠 7. 強化版指令規則：強制隔離歷史記憶
            if sql_data_found and "【📊 資料庫精確查詢結果】" in full_context:
                instruction_rule = (
                    "【最高回答準則 - 嚴格遵守】\n"
                    "1. 【唯一真理】：請『絕對無視』對話紀錄中出現過的所有數字！你的答案『只能』是上方資料庫剛剛查出的數字。\n"
                    "2. 嚴禁重複上一題的答案！不要自己通靈！\n"
                    "3. 請用符合角色的口吻，自然地把數字講出來。嚴禁直接輸出「【資料庫精確查詢結果】」或「答案：」這種機器人標籤。\n"
                    "4. 請全程使用「正體中文」回答，禁止使用簡體字。\n"
                )
            elif not sql_data_found:
                # 把防護也加在補底機制上
                instruction_rule = (
                    "【最高回答準則】：請直接參考上方的『當前帳戶餘額概況』與『本月收支參考數據』來回答。\n"
                    "嚴禁向小主人要數據！嚴禁重複過去對話中的問答紀錄！"
                )
            else:
                instruction_rule = "請老實告訴小主人系統查不到這筆資料，不准向小主人索要數據。"
                
                
            # 最終 Prompt 組合：直接組裝字串，徹底刪除多餘的 final_prompt 解決 Pylance 黃線！
            prompt = f"""
            [角色設定]
            {current_persona}

            [🚨 數據查詢結果 - 最高優先權]
            {full_context}

            [執行準則]
            {BASE_RULES}
            {instruction_rule}
            """
            
            # ✅ 補上 confidence
            return {"intent": intent, "system_prompt": prompt, "confidence": confidence}

        else:
            # 補底防噴
            # ✅ 補上 confidence
            return {"intent": "CHAT", "system_prompt": CHAT_TEMPLATE.format(today=today, persona=current_persona, rules=BASE_RULES), "confidence": confidence}

    @staticmethod
    def execute_record_chain(system_prompt: str, user_message: str) -> dict:
        from pydantic import SecretStr
        from langchain_core.output_parsers import PydanticOutputParser
        from ..schemas.bot_schema import RecordResponseSchema

        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            raise ValueError("找不到 GROQ_API_KEY，請確認 .env 檔案設定喵！")

        secure_api_key = SecretStr(groq_api_key)
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0, api_key=secure_api_key)
        parser = PydanticOutputParser(pydantic_object=RecordResponseSchema)

        strict_json_rules = (
            "【最高指令：絕對禁止任何廢話】\n"
            "請你扮演一個無情的資料轉換機，你唯一的任務就是輸出符合格式的 JSON 字典。\n"
            "1. 絕對不允許在 JSON 之前或之後加上任何文字。\n"
            "2. 請直接以 `{` 開頭，並以 `}` 結尾。\n"
            "3. 不要使用 ```json 的 Markdown 標籤，只輸出純文字格式的 JSON。\n"
            "4. ⚠️ 【日期格式強制規定】：如果小主人提到「今天」或沒有明確指明日期，請一律使用系統時間的日期！且格式必須嚴格為 YYYY-MM-DD（例如：2026-04-17），絕對不可包含具體時間（HH:MM:SS）或中文字！\n"
        )

        final_prompt = PromptTemplate(
            template="{strict_json_rules}\n{system_prompt}\n\n[小主人的話]：{user_message}",
            input_variables=["strict_json_rules", "system_prompt", "user_message"]
        )

        chain = final_prompt | llm | parser
        result = chain.invoke({
            "strict_json_rules": strict_json_rules,
            "system_prompt": system_prompt,
            "user_message": user_message
        })

        return result.model_dump()
