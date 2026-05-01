# web_app/services/sql_generator_service.py
import os
import re
from pydantic import SecretStr
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

class SQLGeneratorService:
    
    @classmethod
    def _load_schema_context(cls) -> str:
        """從資料夾讀取資料庫地圖 (Schema Collection)"""
        schema_path = "./web_app/data/secret/schema_collection.md"
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return "Error: schema_collection.md not found."

    @classmethod
    def _self_correction(cls, sql: str, user_id: int) -> str:
        """
        反思機制 (Self-Correction)：以最嚴格的規則校查生成的 SQL。
        如果發現致命錯誤，直接在此進行字符串修復。
        """
        sql = sql.strip()
        
        # 1. 強制檢查 WHERE user_id 隔離性
        user_clause = f"user_id = {user_id}"
        if user_clause not in sql:
            if "WHERE" in sql.upper():
                sql = re.sub(r"WHERE", f"WHERE {user_clause} AND", sql, flags=re.IGNORECASE)
            else:
                sql += f" WHERE {user_clause}"

        # 2. 強制清理所有 Markdown 標籤與換行
        sql = sql.replace("```sql", "").replace("```", "").replace("\n", " ")
        sql = re.sub(r'\s+', ' ', sql).strip()

        # 3. LIKE 語法精確化：拔除百分比符號內的異常空格
        sql = re.sub(r"LIKE\s+'%\s+", "LIKE '%", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\s+%'", "%'", sql, flags=re.IGNORECASE)

        return sql

    SCHEMA_PROMPT_TEMPLATE = """
    你是一個專業的 MySQL 專家。你唯一的工作是將使用者的問題轉化為精確的 SQL 語句。

    【重要時間指引】
    [日曆資訊]：今天是 {today_str} ({weekday_str})。
    - 如果問「本月」或「這個月」，範圍是 {this_month_start} 到 {this_month_end}。
    - 如果問「上個月」，範圍是 {last_month_start} 到 {last_month_end}。
    - 如果問「本週」或「這週」，範圍是 {this_week_start} 到 {this_week_end}。
    - 如果問「今年以來」，範圍是 {this_year_start} 到 {today_str}。
    - 你擁有查詢過去 6 個月所有帳務的權限。
    
    【🛡️ 絕對安全禁令】
    1. 你只有「讀取」資料庫的權限！
    2. 你的輸出必須永遠以 `SELECT` 開頭。
    3. 絕對禁止生成 `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER` 等任何會修改資料庫的語法，違者將受嚴厲懲罰！

    【📚 第三層：資料庫架構地圖】
    {dynamic_schema}
    
    【⚠️ 執行準則 - 違者懲罰】
    1. 僅輸出 SQL，嚴禁任何解釋。
    2. 收支判定：支出 add_type = 0，收入 add_type = 1。
    3. 項目查詢：如果小主人提到具體活動、物品或店家，【絕對禁止】只用 add_class 查詢，必須強制加上 `add_note LIKE '%關鍵字%'` 來精準比對！
    4. 時間範圍：本月為 `add_date BETWEEN '{this_month_start}' AND '{this_month_end}'`。
    5. 會員隔離：必須包含 `user_id = {user_id}`。

    【🚨 轉帳查詢特別規定】
    - 如果使用者問的是「轉帳」，請務必檢查轉帳資料表的正確名稱與欄位！
    - 嚴禁把記帳表的 `add_date` 拿到轉帳表去用！

    【⚠️ 搜尋鐵律】
    1. 必須包含 `WHERE user_id = {user_id}`。
    2. 收入 add_type=1, 支出 add_type=0。
    3. 日期篩選必須精確到天（BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'）。
    """

    @classmethod
    async def generate_sql(cls, user_query: str, user_id: int) -> tuple[str, bool, dict]:
        api_key_str = os.getenv("GROQ_API_KEY")
        if not api_key_str: 
            return "", False, {} # 🌟 沒給鑰匙就回傳空帳單

        from datetime import datetime, timedelta
        import calendar
        from .vector_db_tools import VectorDBTools

        now = datetime.now()
        # 🌟 time_vars 是準備在「最後一刻」才注入模板的真實變數
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

        # ==========================================
        # 🌟 啟動快取攔截機制
        # ==========================================
        cached_sql_template = VectorDBTools.get_cached_sql(user_query)
        if cached_sql_template:
            try:
                final_cached_sql = cached_sql_template.format(**time_vars)
                final_sql = cls._self_correction(final_cached_sql, user_id)
                print("⚡ [SQL 快取加速] 省下了 3500 Token 和 3 秒的等待時間！")
                # 🌟 修正 2：快取命中，回傳真實的 0 Token 帳單！
                return final_sql, True, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            except Exception as e:
                print(f"⚠️ 快取模板注入失敗... ({e})")

        # ==========================================
        # 去問 Groq
        # ==========================================
        schema_context = cls._load_schema_context()
        secure_key = SecretStr(api_key_str)
        # llama-3.3-70b-versatile
        llm = ChatGroq(model="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0, api_key=secure_key)

        # 🌟 核心防護 1：在 Prompt 中使用雙大括號 {{}}，確保 LangChain 不會提早把變數解開！
        # 這樣 Groq 產出的 SQL 才會乖乖帶著 {user_id} 這幾個英文字母，而不是具體的數字。
        SCHEMA_PROMPT_TEMPLATE = """
        你是一個專業的 MySQL 專家。你唯一的工作是將使用者的問題轉化為精確的 SQL 語句。
        
        【🚨 極度重要：時間與身分變數模板規則】
        你產出的 SQL 絕對不可寫死具體的日期字串或 user_id 數字！必須原封不動地使用以下「大括號變數」：
        - 若查「今天」，日期請寫 `'{{today_str}}'`
        - 若查「本月」，日期請寫 `BETWEEN '{{this_month_start}}' AND '{{this_month_end}}'`
        - 若查「上個月」，日期請寫 `BETWEEN '{{last_month_start}}' AND '{{last_month_end}}'`
        - 若查「本週」，日期請寫 `BETWEEN '{{this_week_start}}' AND '{{this_week_end}}'`
        - 若查「今年」，日期請寫 `BETWEEN '{{this_year_start}}' AND '{{today_str}}'`
        - 會員隔離：必須包含 `user_id = {{user_id}}`
        
        【現在日曆參考 (僅供理解語意，請勿寫死在 SQL 中)】
        今天是 {current_date} ({current_weekday})。

        【🛡️ 絕對安全禁令】
        1. 只有「讀取」權限！必須以 `SELECT` 開頭。
        2. 絕對禁止 `INSERT`, `UPDATE`, `DELETE`, `DROP` 等。

        【📚 資料庫架構地圖】
        {dynamic_schema}
        
        【⚠️ 查詢鐵律 (IF-ELSE 分流)】
        當判斷查詢為「支出 (add_type=0)」或「收入 (add_type=1)」時，請嚴格遵守以下互斥規則，僅輸出 SQL：

        [情況 A：查詢大分類] (如：飲食、交通、居家、娛樂)
        絕對禁止使用 LIKE！必須利用 LEFT JOIN 確保複合訂單被正確拆分：
        SELECT SUM(COALESCE(add_items.item_amount, adds.add_amount))
        FROM adds LEFT JOIN add_items ON adds.add_id = add_items.add_id
        WHERE adds.user_id = {{user_id}} AND adds.add_type = 0
        AND COALESCE(add_items.item_class, adds.add_class) = '目標分類'
        AND adds.add_date BETWEEN '...' AND '...'

        [情況 B：查詢具體物品/店家] (如：咖啡、便當、麥當勞)
        不需要 JOIN！直接從主表用 LIKE 精準比對：
        SELECT SUM(add_amount) FROM adds
        WHERE user_id = {{user_id}} AND add_type = 0
        AND (add_note LIKE '%關鍵字%' OR add_tag LIKE '%關鍵字%')
        AND adds.add_date BETWEEN '...' AND '...'
        """

        prompt = ChatPromptTemplate.from_messages([
            ("system", SCHEMA_PROMPT_TEMPLATE),
            ("human", "問題：{query}")
        ])

        chain = prompt | llm
        try:
            # 這裡只傳遞給 Prompt 幫助理解的日曆，不再傳入具體變數
            invoke_args = {
                "current_date": now.strftime('%Y-%m-%d'),
                "current_weekday": calendar.day_name[now.weekday()],
                "dynamic_schema": schema_context, 
                "query": user_query
            }
            response = await chain.ainvoke(invoke_args)

            # 🌟 修正 3：從 Groq 的回應裡，把真實的 Token 帳單挖出來！
            sql_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                sql_usage["prompt_tokens"] = response.usage_metadata.get("input_tokens", 0)
                sql_usage["completion_tokens"] = response.usage_metadata.get("output_tokens", 0)
                sql_usage["total_tokens"] = response.usage_metadata.get("total_tokens", 0)

            raw_sql = str(response.content)
            clean_template = raw_sql.replace("```sql", "").replace("```", "").replace("\n", " ").strip()
            clean_template = re.sub(r'\s+', ' ', clean_template)
            clean_template = re.sub(r"user_id\s*=\s*\d+", "user_id = {user_id}", clean_template, flags=re.IGNORECASE)
            
            if clean_template.lower().startswith("select"):
                VectorDBTools.save_sql_to_cache(user_query, clean_template)

            final_sql = clean_template.format(**time_vars)
            final_sql = cls._self_correction(final_sql, user_id)
            
            # 🌟 修正 4：把挖出來的 sql_usage 一併回傳！
            return final_sql, False, sql_usage
        except Exception as e:
            print(f"❌ SQL Generator 致命錯誤: {e}")
            return "", False, {}