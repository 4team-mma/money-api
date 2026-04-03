# web_app/services/finance_agent_service.py
from sqlalchemy.orm import Session
from sqlalchemy import desc, text
from .finance_tools import FinanceTools
from ..models import CpiData, Member
import re
from datetime import datetime
import pytz
import os

# 🌟 引入所有需要的模板
from ..prompts.system_prompts import (
    PERSONAS, BASE_RULES, CHAT_TEMPLATE,
    ADVISOR_TEMPLATE, RECORD_TEMPLATE,
    QUERY_TEMPLATE, KNOWLEDGE_TEMPLATE
)

# 🌟 引入 LangChain 與 Groq 需要的套件
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from ..schemas.bot_schema import RecordResponseSchema


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
            "有沒有", "吃了沒", "買了沒", "過", "紀錄", "查詢", "找一下"
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
    async def get_context(db: Session, user: Member, message: str, persona_key: str | None = "cute", override_intent: str | None = None) -> dict:

        user_id = user.user_id

        # 🛡️ 核心修正：定義 clean_query，解決 UndefinedVariable 並過濾雜訊
        clean_query = message
        if "小主人說：" in message:
            clean_query = message.split("小主人說：")[-1]
        elif "]" in message:
            clean_query = message.split("]")[-1]
        clean_query = re.sub(r'\[系統指令.*?\]', '', clean_query).strip()

        # 分析意圖
        intent = override_intent if override_intent else FinanceAgentService.analyze_intent(message)

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
            return {"intent": "CHAT", "system_prompt": prompt}

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
            return {"intent": intent, "system_prompt": prompt}

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
            return {"intent": intent, "system_prompt": prompt}

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
            return {"intent": "KNOWLEDGE", "system_prompt": prompt}


        # ==========================================
        # 💡 意圖 E：智能數據查詢 (混合 Text-to-SQL 模式)
        # ==========================================
        elif intent in ["QUERY", "MULTI_QUERY"]:
            # 🚀 權限覺醒：告訴 AI 它看得到所有歷史紀錄
            db_info = "【📁 帳本權限資訊】: 你擁有從 2026-01-01 至今的所有歷史明細權限。"
            context_parts = [f"[系統時間]: {today}", db_info]

            from .sql_generator_service import SQLGeneratorService
            from ..database import SessionLocal
            sql_data_found = False

            try:
                # 🛡️ 擷取乾淨訊，避免標籤干擾
                clean_query = message.split("小主人說：")[-1] if "小主人說：" in message else message
                clean_query = re.sub(r'\[系統指令.*?\]', '', clean_query).strip()

                generated_sql = await SQLGeneratorService.generate_sql(clean_query, user_id)
                print(f"🕵️‍♂️ [SQL 引擎啟動]：{generated_sql}")

                if generated_sql and generated_sql.lower().startswith("select"):
                    with SessionLocal() as db_session:
                        result = db_session.execute(text(generated_sql))
                        sql_result = result.fetchall()

                        # 🛡️ 核心修復：強制轉成整數，並處理查無紀錄(None)的情況
                        if sql_result:
                            # 如果 SUM 回傳 None (代表查無此類別支出)，我們強制給 0
                            raw_val = sql_result[0][0] if sql_result[0][0] is not None else 0
                            precise_val = int(round(float(raw_val)))

                            # 🔥 隔離機制：只要有 SQL 結果，就覆蓋掉原本的 context
                            context_parts = [
                                f"【🚨 資料庫唯一正確數據】: 經過系統查詢，該項目的總金額結果為「{precise_val}」元。",
                                "🛑 重要：請絕對無視歷史對話中的任何數字，以此數據為唯一標準回答小主人。"
                            ]
                            sql_data_found = True
                        else:
                            context_parts.append(f"【⚠️ 查詢結果】: 資料庫搜尋回報，找不到關於「{clean_query}」的紀錄。")
                            sql_data_found = True # 設為 True 避免觸發「只有一個月」的錯誤保底
            except Exception as e:
                print(f"❌ SQL 執行報警: {e}")
                context_parts.append(f"【⚠️ 系統異常】: 資料庫連線失敗，請小主人稍後再試。")

            # 🚀 隔離邏輯：只有 SQL 失敗時，才提供補底參考
            if not sql_data_found:
                context_parts.append("【📊 當前帳戶餘額概況】")
                context_parts.append(FinanceTools.get_account_summary(db, user_id))
                context_parts.append("【📅 本月收支參考數據(4月)】")
                context_parts.append(FinanceTools.get_monthly_stats(db, user_id))

            full_context = "\n\n".join(context_parts)

            # 🧠 強化人性化指令，並強迫它使用整數回答
            if sql_data_found and "【🚨 資料庫唯一正確數據】" in full_context:
                instruction_rule = (
                    "你現在是專業會計喵。請遵循以下指令：\n"
                    "1. 必須且只能依照 [資料庫唯一正確數據] 裡的整數回答小主人。\n"
                    "2. 禁止在金額中使用小數點。新台幣沒有小數點喵！\n"
                    "3. 如果數據是 0，請溫柔地說：『喵嗚...喵喵翻遍帳本都沒看到這筆紀錄，小主人這段時間應該沒買過這個喔！』\n"
                    "4. 禁止說自己只有一個月權限，因為你已經查過資料庫了。"
                )
            else:
                instruction_rule = "請溫柔提示找不到資料，並建議小主人檢查日期或類別（如：三月、上個月）喵。"

            prompt = QUERY_TEMPLATE.format(
                full_context=full_context,
                persona=current_persona,
                rules=BASE_RULES,
                instruction_rule=instruction_rule
            )
            return {"intent": "QUERY", "system_prompt": prompt}

        else:
            # 補底防噴
            return {"intent": "CHAT", "system_prompt": CHAT_TEMPLATE.format(today=today, persona=current_persona, rules=BASE_RULES)}

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
