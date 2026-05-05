# web_app/services/sql_generator_service.py
import os
import re
from pydantic import SecretStr
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session
from ..models import AddRecord
from datetime import datetime, timedelta
import calendar
from .vector_db_tools import VectorDBTools


class SQLGeneratorService:
    
    # 🛡️ 禁止查詢的敏感資料表（絕對不能碰）
    FORBIDDEN_TABLES = {
        "members", "ai_config", "token_usage_logs", 
        "intent_review_logs", "security_audit_logs", "login_activities"
    }

    # 🛡️ 禁止出現在 SELECT 區段的敏感欄位
    FORBIDDEN_COLUMNS = {
        "password", "api_key", "notion_api_key", "notion_page_id",
        "secret", "token", "hash", "salt", "refresh_token"
    }

    # ✅ 只允許查詢這些表
    ALLOWED_TABLES = {
        "adds", "add_items", "accounts", "transactions", 
        "budgets", "savings_goals", "reminders", "cpi_data", "salary_data"
    }

    @classmethod
    def _load_schema_context(cls) -> str:
        schema_path = "./web_app/data/secret/schema_collection.md"
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return "Error: schema_collection.md not found."

    @classmethod
    def _self_correction(cls, sql: str, user_id: int) -> str:

        sql = sql.strip()

        # 1. 先清 SQL 單行註解 -- (會把後面條件整行吃掉)
        sql = re.sub(r'--[^\n]*', ' ', sql)

        # 2. 清 Markdown 說明文字 (### 之後全部丟掉)
        sql = re.sub(r'###.*', '', sql, flags=re.DOTALL)

        # 3. 清多行註解 /* */
        sql = re.sub(r'/\*.*?\*/', ' ', sql, flags=re.DOTALL)

        # 4. 強制檢查 WHERE user_id 隔離性
        user_clause = f"user_id = {user_id}"
        if user_clause not in sql:
            if "WHERE" in sql.upper():
                sql = re.sub(r"WHERE", f"WHERE {user_clause} AND", sql, flags=re.IGNORECASE)
            else:
                sql += f" WHERE {user_clause}"

        # 5. 清 Markdown 標籤與換行
        sql = sql.replace("```sql", "").replace("```", "").replace("\n", " ")
        sql = re.sub(r'\s+', ' ', sql).strip()

        # 6. LIKE 語法精確化
        sql = re.sub(r"LIKE\s+'%\s+", "LIKE '%", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\s+%'", "%'", sql, flags=re.IGNORECASE)

        return sql


    @classmethod
    def _validate_sql_safety(cls, sql: str, user_id: int) -> tuple[bool, str]:
        """🛡️ SQL 安全驗證器：防止敏感資料外洩與跨用戶查詢"""
        sql_upper = sql.upper()
        
        # 1. 只允許 SELECT
        if not sql_upper.strip().startswith("SELECT"):
            return False, "只允許 SELECT 語句"
        
        # 2. 禁止危險 DML/DDL 關鍵字
        FORBIDDEN_KEYWORDS = ["DROP", "DELETE", "UPDATE", "INSERT", 
                            "ALTER", "TRUNCATE", "EXEC", "UNION"]
        for kw in FORBIDDEN_KEYWORDS:
            if kw in sql_upper:
                return False, f"禁止使用 {kw}"
        
        # 3. 禁止查詢敏感資料表
        for table in cls.FORBIDDEN_TABLES:
            # 用單字邊界比對，避免誤判 (例如 add_members 裡面有 member)
            import re as _re
            if _re.search(rf'\b{table}\b', sql, _re.IGNORECASE):
                return False, f"禁止查詢敏感資料表：{table}"
        
        # 4. 禁止在 SELECT 區段出現敏感欄位
        # 只取 SELECT ... FROM 中間的部分來驗證
        select_match = _re.search(r'SELECT\s+(.+?)\s+FROM', sql, _re.IGNORECASE | _re.DOTALL)
        if select_match:
            select_part = select_match.group(1).upper()
            for col in cls.FORBIDDEN_COLUMNS:
                if col.upper() in select_part:
                    return False, f"禁止查詢敏感欄位：{col}"
        
        # 5. 強制確認 user_id 隔離
        if str(user_id) not in sql:
            return False, "缺少 user_id 隔離條件，疑似跨用戶查詢"
        
        return True, "OK"



    @classmethod
    async def generate_sql(cls, user_query: str, user_id: int, db: Session) -> tuple[str, bool, dict, str]:
        api_key_str = os.getenv("GROQ_API_KEY")
        if not api_key_str:
            return "", False, {}, ""

        # 動態撈取該使用者的合法分類清單
        user_classes_raw = db.query(AddRecord.add_class).filter(
            AddRecord.user_id == user_id
        ).distinct().all()
        valid_classes = [c[0] for c in user_classes_raw if c[0]]
        valid_classes_str = "、".join(valid_classes) if valid_classes else "目前尚無分類"

        now = datetime.now()
        time_vars = {
            "today_str": now.strftime('%Y-%m-%d'),
            "this_year_start": now.replace(month=1, day=1).strftime('%Y-%m-%d'),
            "this_month_start": now.replace(day=1).strftime('%Y-%m-%d'),
            "user_id": user_id
        }
        next_month = now.replace(day=28) + timedelta(days=4)
        time_vars["this_month_end"] = (next_month - timedelta(days=next_month.day)).strftime('%Y-%m-%d')
        last_month_end = (now.replace(day=1) - timedelta(days=1))
        time_vars["last_month_start"] = last_month_end.replace(day=1).strftime('%Y-%m-%d')
        time_vars["last_month_end"] = last_month_end.strftime('%Y-%m-%d')
        start_of_week = now - timedelta(days=now.weekday())
        time_vars["this_week_start"] = start_of_week.strftime('%Y-%m-%d')
        time_vars["this_week_end"] = (start_of_week + timedelta(days=6)).strftime('%Y-%m-%d')

        # 快取攔截
        cached_sql_template = VectorDBTools.get_cached_sql(user_query)
        if cached_sql_template:
            try:
                final_cached_sql = cached_sql_template.format(**time_vars)
                final_sql = cls._self_correction(final_cached_sql, user_id)
                print("⚡ [SQL 快取加速] 命中！")
                return final_sql, True, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},""
            except Exception as e:
                print(f"⚠️ 快取模板注入失敗... ({e})")

        schema_context = cls._load_schema_context()
        secure_key = SecretStr(api_key_str)
        llm = ChatGroq(model="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0, api_key=secure_key)

        SCHEMA_PROMPT_TEMPLATE = """
        你是一個專業的 MySQL 專家。你唯一的工作是將使用者的問題轉化為精確的 SQL 語句。

        【🚨 輸出格式鐵律】
        1. 只能輸出純 SQL 語句，從 SELECT 開始，到最後一個條件結束。
        2. 絕對禁止輸出任何註解（-- 或 /* */）、Markdown、說明文字、換行。
        3. 違反此規定將導致系統崩潰。
        

        【🚨 時間與身分變數規則】
        SQL 中絕對不可寫死日期或 user_id，必須使用以下變數：
        - 查今天：'{{today_str}}'
        - 查本月：BETWEEN '{{this_month_start}}' AND '{{this_month_end}}'
        - 查上個月：BETWEEN '{{last_month_start}}' AND '{{last_month_end}}'
        - 查本週：BETWEEN '{{this_week_start}}' AND '{{this_week_end}}'
        - 查今年：BETWEEN '{{this_year_start}}' AND '{{today_str}}'
        - 會員隔離：user_id = {{user_id}}

        【現在日曆 (僅供語意理解，禁止寫死在 SQL)】
        今天是 {current_date} ({current_weekday})。

        【🛡️ 類別與關鍵字鐵律：嚴禁自動歸類！！！】
        合法大分類清單：[{valid_classes_list}]
        
        🚨 警告：你絕對不可以使用你的常識來幫物品分類！
        如果小主人問的是「買衣服」、「咖啡」、「便當」，就算你覺得它屬於「購物」或「飲食」，你也絕對禁止把它擅自替換成 `add_class = '購物'`！
        只要小主人的「原話」沒有一模一樣出現在合法清單中，就必須強制走 [情況 B]！

        【⚠️ 查詢鐵律 — 嚴格二選一，絕對不可混用】

        [情況 A] 小主人的「原話」完全等於合法清單中的詞 (例如他明確問「購物花了多少」)
        → 只用 add_class，禁止加 LIKE
        SELECT SUM(COALESCE(ai.item_amount, a.add_amount))
        FROM adds a LEFT JOIN add_items ai ON a.add_id = ai.add_id
        WHERE a.user_id = {{user_id}} AND a.add_type = 0
        AND COALESCE(ai.item_class, a.add_class) = '目標分類'
        AND a.add_date BETWEEN '...' AND '...'

        [情況 B] 小主人問的是具體物品或行為 (目標不在清單內)
        → 只用 LIKE 精準比對，絕對禁止擅自加上 add_class！
        
        【🚨 關鍵字萃取鐵律：去除動詞，保留核心名詞】
        小主人說話時常帶有動詞（買、吃、喝、看、繳），但資料庫備註通常只記名詞。
        請你務必聰明地「去除動詞」，只把「核心實體名詞」放進 LIKE 裡面！
        - 錯誤示範：「買衣服」 -> LIKE '%買衣服%' (會漏掉只寫'衣服'的紀錄)
        - 正確示範：「買衣服」 -> LIKE '%衣服%'
        - 正確示範：「吃包子」 -> LIKE '%包子%'
        - 正確示範：「繳電費」 -> LIKE '%電費%'
        
        SELECT SUM(add_amount) FROM adds
        WHERE user_id = {{user_id}} AND add_type = 0
        AND (add_note LIKE '%關鍵字%' OR add_tag LIKE '%關鍵字%')
        AND add_date BETWEEN '...' AND '...'
        (💡 提示：關鍵字請保留小主人的完整動名詞，例如 '%買衣服%')

        【🚨 致命禁令】禁止把 add_class='...' 和 LIKE 用 AND 串在一起！

        【🛡️ 安全禁令】只有 SELECT 權限，禁止 INSERT、UPDATE、DELETE、DROP、ALTER。

        【🚨 轉帳查詢】問到轉帳請用 transactions 表，禁止用 adds 的 add_date。

        【🚨 預算查詢鐵律】
        當問題涉及「預算」、「還剩多少」、「預算夠嗎」時：
        1. 必須查 budgets 表，絕對禁止只查 adds 表。
        2. 絕對禁止 JOIN add_items 表。
        3. JOIN 條件必須是 b.category = a.add_class，禁止出現 ai.item_class。
        4. 只 SELECT remaining 一個欄位，正確結構：
        SELECT b.amount - COALESCE(SUM(a.add_amount), 0) AS remaining FROM budgets b LEFT JOIN adds a ON b.user_id = a.user_id AND b.category = a.add_class AND a.add_type = 0 AND a.add_date BETWEEN '{{this_month_start}}' AND '{{this_month_end}}' WHERE b.user_id = {{user_id}} AND b.category = '類別' GROUP BY b.budget_id

        【📚 資料庫架構】
        {dynamic_schema}
        """

        prompt = ChatPromptTemplate.from_messages([
            ("system", SCHEMA_PROMPT_TEMPLATE),
            ("human", "問題：{query}")
        ])

        chain = prompt | llm
        try:
            invoke_args = {
                "current_date": now.strftime('%Y-%m-%d'),
                "current_weekday": calendar.day_name[now.weekday()],
                "valid_classes_list": valid_classes_str,
                "dynamic_schema": schema_context,
                "query": user_query
            }
            response = await chain.ainvoke(invoke_args)

            sql_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                sql_usage["prompt_tokens"] = response.usage_metadata.get("input_tokens", 0)
                sql_usage["completion_tokens"] = response.usage_metadata.get("output_tokens", 0)
                sql_usage["total_tokens"] = response.usage_metadata.get("total_tokens", 0)

            raw_sql = str(response.content)
            clean_template = raw_sql.replace("```sql", "").replace("```", "").replace("\n", " ").strip()
            clean_template = re.sub(r'\s+', ' ', clean_template)

            # LLM 前面加了中文解釋就強制只取 SELECT 之後的部分
            select_match = re.search(r'(SELECT\s+.+)', clean_template, flags=re.IGNORECASE)
            if select_match:
                clean_template = select_match.group(1).strip()
            else:
                print("❌ [SQL Generator] LLM 沒有生成有效的 SELECT 語句")
                return "", False, {},""

            # user_id 和日期都模板化
            clean_template = re.sub(r"user_id\s*=\s*\d+", "user_id = {user_id}", clean_template, flags=re.IGNORECASE)
            clean_template = re.sub(r"'" + now.replace(day=1).strftime('%Y-%m-%d') + r"'", "'{this_month_start}'", clean_template)
            clean_template = re.sub(r"'" + time_vars["this_month_end"] + r"'", "'{this_month_end}'", clean_template)
            clean_template = re.sub(r"'" + time_vars["last_month_start"] + r"'", "'{last_month_start}'", clean_template)
            clean_template = re.sub(r"'" + time_vars["last_month_end"] + r"'", "'{last_month_end}'", clean_template)
            clean_template = re.sub(r"'" + now.strftime('%Y-%m-%d') + r"'", "'{today_str}'", clean_template)
            clean_template = re.sub(r"'" + time_vars["this_week_start"] + r"'", "'{this_week_start}'", clean_template)
            clean_template = re.sub(r"'" + time_vars["this_week_end"] + r"'", "'{this_week_end}'", clean_template)

            # if clean_template.lower().startswith("select") and cls._is_safe_to_cache(clean_template):
            #     VectorDBTools.save_sql_to_cache(user_query, clean_template)

            final_sql = clean_template.format(**time_vars)
            final_sql = cls._self_correction(final_sql, user_id)
            
            # 🛡️ 新增：安全驗證關卡
            is_safe, reason = cls._validate_sql_safety(final_sql, user_id)
            if not is_safe:
                print(f"🚫 [SQL 安全攔截] 拒絕執行：{reason} | SQL: {final_sql[:100]}")
                return "", False, {}, ""  # 直接回傳空字串，不執行

            return final_sql, False, sql_usage, clean_template
        except Exception as e:
            print(f"❌ SQL Generator 致命錯誤: {e}")
            return "", False, {},""

    # ✅ 放在 generate_sql 方法外，但在 class 內，加 @staticmethod
    @staticmethod
    def _is_safe_to_cache(sql: str) -> bool:
        """防止含字串欄位的壞 SQL 被存入快取"""
        if "budgets" in sql.lower():
            select_part = re.search(r'SELECT\s+(.+?)\s+FROM', sql, re.IGNORECASE)
            if select_part and "b.category" in select_part.group(1).lower():
                print("⚠️ [快取防護] 含字串欄位的 budget SQL，跳過快取")
                return False
        return True