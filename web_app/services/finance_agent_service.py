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

# 🚀 引入妳新定義的兩顆大腦與 V2 需要的 NLP 引擎
from .finance_agent_v1_service import FinanceAgentV1Service
from .finance_agent_mixai_service import FinanceAgentMixAIService
# from ..services.nlp.context import IntentContext
# from ..services.nlp.engine import RuleEngine

class FinanceAgentService:

    @staticmethod
    def _clean_message(message: str) -> str:
        """統一的訊息清洗邏輯，拿掉 [系統指令] 標籤"""
        latest_msg = message
        if "小主人說：" in message:
            latest_msg = message.split("小主人說：")[-1]
        elif "]" in message:
            latest_msg = message.split("]")[-1]
        
        # 清除系統指令並轉小寫，並去除頭尾空白
        return re.sub(r'\[系統指令.*?\]', '', latest_msg).strip()

    @staticmethod
    def analyze_intent(message: str) -> str:
        """此方法現在僅作為 V1 的捷徑入口，供舊有代碼相容使用"""
        clean_msg = FinanceAgentService._clean_message(message)
        return FinanceAgentV1Service.analyze_intent(clean_msg)

    @staticmethod
    async def get_context(
        db: Session, 
        user: Member, 
        message: str, 
        persona_key: str | None = "cute", 
        override_intent: str | None = None,
        version: str = "v1"
        ) -> dict:

        user_id = user.user_id

        # 🛡️ 1. 定義 clean_query (這是給 KNOWLEDGE 或 QUERY 檢索用的)
        clean_query = FinanceAgentService._clean_message(message)
        
        # 🧠 2. 確定大腦版本並取得意圖
        if override_intent:
            intent = override_intent
            confidence = 1.0
        elif version == "v2":
            # ✅ 調用 V2 旗艦大腦 (傳入乾淨字串，觸發 NLP 跑分引擎)
            mix_res = FinanceAgentMixAIService.analyze_intent(clean_query)
            intent = mix_res["final_intent"]
            confidence = mix_res["confidence"]
            
            # 詳細 Debug 報告
            print(f"🧠 [V2 大腦診斷報告]")
            print(f"   > 原始訊息: {message[:30]}...")
            print(f"   > 清洗後訊息: {clean_query}")
            print(f"   > ONNX 初判: {mix_res.get('predicted_intent')} ({mix_res.get('confidence'):.2f})")
            print(f"   > 規則修正後: {intent}")
        else:
            # 🏠 調用 V1 舊大腦 (維持原本 Regex 邏輯)
            intent = FinanceAgentV1Service.analyze_intent(clean_query)
            confidence = 1.0
            print(f"🏠 [V1 大腦啟動] 意圖: {intent}")

        # ⏰ 取得當前時間
        tw_tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(tw_tz)
        today = now.strftime('%Y-%m-%d %H:%M:%S')

        safe_persona_key = persona_key if persona_key else "cute"
        current_persona = PERSONAS.get(safe_persona_key, PERSONAS["cute"])

        # ==========================================
        # 💡 意圖分流組合 Prompt (依序為：CHAT, ADVISOR, RECORD, KNOWLEDGE, QUERY)
        # ==========================================
        
        # A: 純閒聊 (CHAT)
        if intent == "CHAT":
            prompt = CHAT_TEMPLATE.format(today=today, persona=current_persona, rules=BASE_RULES)
            return {"intent": "CHAT", "system_prompt": prompt, "confidence": confidence}

        # B: 理財顧問 (ADVISOR)
        elif intent in ["ADVISOR", "MULTI_ADVISOR"]:
            from .advisor_tools import FinancialAdvisorService
            abnormal_report = await FinancialAdvisorService.get_ai_context(db, user)
            prompt = ADVISOR_TEMPLATE.format(today=today, persona=PERSONAS["professional"], abnormal_report=abnormal_report)
            return {"intent": intent, "system_prompt": prompt, "confidence": confidence}

        # C: 記帳 (RECORD)
        elif intent in ["RECORD", "MULTI_RECORD"]:
            from ..models import Account
            first_acc = db.query(Account).filter(Account.user_id == user_id).first()
            default_acc_name = first_acc.account_name if first_acc else "我的錢包"
            parser = PydanticOutputParser(pydantic_object=RecordResponseSchema)
            prompt = RECORD_TEMPLATE.format(today=today, persona=current_persona, default_acc_name=default_acc_name, format_instructions=parser.get_format_instructions())
            return {"intent": intent, "system_prompt": prompt, "confidence": confidence}

        # D: 系統手冊 (KNOWLEDGE)
        elif intent in ["KNOWLEDGE", "MULTI_KNOWLEDGE"]:
            from .vector_db_tools import VectorDBTools
            retrieved_docs = VectorDBTools.search_manual(clean_query)
            prompt = KNOWLEDGE_TEMPLATE.format(today=today, persona=current_persona, rules=BASE_RULES, retrieved_docs=retrieved_docs)
            return {"intent": intent, "system_prompt": prompt, "confidence": confidence}

        # E: 智能數據查詢 (Text-to-SQL 完整邏輯)
        elif intent in ["QUERY", "MULTI_QUERY"]:
            db_info = "【📁 帳本權限資訊】: 你擁有從 2026-01-01 至今的所有歷史明細權限。"
            context_parts = [f"[系統時間]: {today}", db_info]

            from .sql_generator_service import SQLGeneratorService
            from ..database import SessionLocal
            sql_data_found = False
            precise_val = 0

            try:
                # 呼叫重構後的 SQL 引擎
                generated_sql = await SQLGeneratorService.generate_sql(clean_query, user_id)
                print(f"🕵️‍♂️ [SQL 引擎啟動]：{generated_sql}")

                if generated_sql and generated_sql.lower().startswith("select"):
                    with SessionLocal() as db_session:
                        result = db_session.execute(text(generated_sql))
                        sql_result = result.fetchall()
                        if sql_result:
                            raw_val = sql_result[0][0] if sql_result[0][0] is not None else 0
                            # 🛡️ 防呆：如果 SQL 沒有 SUM，多筆資料只取第一筆會造成幻覺
                            # 應由 SQLGeneratorService 確保 aggregate query，這裡加上警告 log
                            if len(sql_result) > 1:
                                print(f"⚠️ [SQL 警告] 查詢回傳 {len(sql_result)} 筆，疑似缺少 SUM()，只取第一筆可能不準確")
                            precise_val = int(round(float(raw_val)))
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

            if not sql_data_found:
                context_parts.append("【📊 當前帳戶餘額概況】")
                context_parts.append(FinanceTools.get_account_summary(db, user_id))
                context_parts.append("【📅 本月收支參考數據(4月)】")
                context_parts.append(FinanceTools.get_monthly_stats(db, user_id))
            
            full_context = "\n\n".join(context_parts)

            if sql_data_found and "【📊 資料庫精確查詢結果】" in full_context:
                instruction_rule = (
                    "【最高回答準則 - 嚴格遵守】\n"
                    "1. 【唯一真理】：請『絕對無視』對話紀錄中出現過的所有數字！你的答案『只能』是上方資料庫剛剛查出的數字。\n"
                    "2. 嚴禁重複上一題的答案！不要自己通靈！\n"
                    "3. 請用符合角色的口吻，自然地把數字講出來。嚴禁直接輸出「【資料庫精確查詢結果】」或「答案：」這種機器人標籤。\n"
                    "4. 請全程使用「正體中文」回答，禁止使用簡體字。\n"
                )
            elif not sql_data_found:
                instruction_rule = (
                    "【最高回答準則】：請直接參考上方的『當前帳戶餘額概況』與『本月收支參考數據』來回答。\n"
                    "嚴禁向小主人要數據！嚴禁重複過去對話中的問答紀錄！"
                )
            else:
                instruction_rule = "請老實告訴小主人系統查不到這筆資料，不准向小主人索要數據。"
                
            prompt = f"""
            [角色設定]
            {current_persona}

            [🚨 數據查詢結果 - 最高優先權]
            {full_context}

            [執行準則]
            {BASE_RULES}
            {instruction_rule}
            """
            return {"intent": intent, "system_prompt": prompt, "confidence": confidence}

        # 最終保底
        return {"intent": "CHAT", "system_prompt": CHAT_TEMPLATE.format(today=today, persona=current_persona, rules=BASE_RULES), "confidence": confidence}

    @staticmethod
    def execute_record_chain(system_prompt: str, user_message: str) -> dict:
        """重構版：使用 8B 小模型 + 動態範例注入 + 陣列暴力淨化器"""
        import json
        import re
        import os
        from pydantic import SecretStr
        from langchain_groq import ChatGroq
        from ..schemas.bot_schema import RecordResponseSchema

        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            raise ValueError("找不到 GROQ_API_KEY，請確認 .env 檔案設定喵！")

        llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0, api_key=SecretStr(groq_api_key))

        db_context_match = re.search(r'【極度重要：小主人的專屬資料庫】[\s\S]*', system_prompt)
        user_db_context = db_context_match.group(0) if db_context_match else ""

        # 🌟 核心修正 1：用 Regex 從 prompt 裡挖出「真正的預設帳戶名稱」
        default_acc_match = re.search(r'\[預設帳戶\]：(.*)', system_prompt)
        default_acc = default_acc_match.group(1).strip() if default_acc_match else "現金"

        # 🌟 核心修正 2：直接把 {default_acc} 寫死在範例裡面，讓 AI 連想都不用想，照抄就對了！
        few_shot_prompt = f"""
你是一個無情的 JSON 轉換機。請將使用者的話轉換為記帳 JSON 格式。
絕對不要輸出任何解釋或 Markdown 標記。只能輸出 `[` 開頭並以 `]` 結尾的 JSON 陣列。
如果有多筆記帳，請放在同一個陣列中。日期未指定請用今天。

{user_db_context}

【轉換範例 1：單筆支出】
[小主人的話]：我今天吃麥當勞花了 150 元
[
  {{
    "record_type": "expense",
    "add_note": "麥當勞",
    "add_amount": 150,
    "record_date": "2026-04-30",
    "add_class": "飲食",
    "add_class_icon": "🍔",
    "account_name": "{default_acc}",
    "add_member": "自己",
    "add_tag": "需要",
    "from_account": "{default_acc}",
    "to_account": "{default_acc}"
  }}
]

【轉換範例 2：多筆支出】
[小主人的話]：搭高鐵花 300，然後買書花 400
[
  {{
    "record_type": "expense",
    "add_note": "高鐵",
    "add_amount": 300,
    "record_date": "2026-04-30",
    "add_class": "交通",
    "add_class_icon": "🚗",
    "account_name": "{default_acc}",
    "add_member": "自己",
    "add_tag": "需要",
    "from_account": "{default_acc}",
    "to_account": "{default_acc}"
  }},
  {{
    "record_type": "expense",
    "add_note": "書",
    "add_amount": 400,
    "record_date": "2026-04-30",
    "add_class": "學習",
    "add_class_icon": "📚",
    "account_name": "{default_acc}",
    "add_member": "自己",
    "add_tag": "想要",
    "from_account": "{default_acc}",
    "to_account": "{default_acc}"
  }}
]

【轉換範例 3：收入與家庭成員】
[小主人的話]：我媽今天給我 200 元零用錢
[
  {{
    "record_type": "income",
    "add_note": "零用錢",
    "add_amount": 200,
    "record_date": "2026-04-30",
    "add_class": "其他",
    "add_class_icon": "💰",
    "account_name": "{default_acc}",
    "add_member": "父母",
    "add_tag": "想要",
    "from_account": "{default_acc}",
    "to_account": "{default_acc}"
  }}
]

【現在換你】
[小主人的話]：{user_message}
"""
        response = llm.invoke(few_shot_prompt)
        
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage["prompt_tokens"] = response.usage_metadata.get("input_tokens", 0)
            usage["completion_tokens"] = response.usage_metadata.get("output_tokens", 0)
            usage["total_tokens"] = response.usage_metadata.get("total_tokens", 0)

        raw_text = str(response.content)
        print(f"🤖 [Groq 8B 原始輸出]:\n{raw_text}")
        
        match = re.search(r"(\[[\s\S]+\])", raw_text)
        clean_json_str = match.group(1) if match else raw_text

        try:
            parsed_data_list = json.loads(clean_json_str)
            if not isinstance(parsed_data_list, list):
                parsed_data_list = [parsed_data_list]

            wrapper_payload = {
                "reply_text": "已幫你記好囉喵！",
                "action_data": parsed_data_list 
            }
            
            validated = RecordResponseSchema(**wrapper_payload)
            dumped_data = validated.model_dump()
            
            return {
                "action_data": dumped_data["action_data"],
                "reply_text": dumped_data["reply_text"],
                "usage": usage 
            }
        except Exception as e:
            print(f"❌ JSON 解析失敗: {e}")
            raise e