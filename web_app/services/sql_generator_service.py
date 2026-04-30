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
    async def generate_sql(cls, user_query: str, user_id: int) -> str:
        api_key_str = os.getenv("GROQ_API_KEY")
        if not api_key_str: return ""

        # 🌟 核心修正：動態計算所有時間邊界
        from datetime import datetime, timedelta
        import calendar

        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        weekday_str = calendar.day_name[now.weekday()] # 取得星期幾
        this_year_start = now.replace(month=1, day=1).strftime('%Y-%m-%d')
        
        # 本月
        this_month_start = now.replace(day=1).strftime('%Y-%m-%d')
        # 找出下個月的第一天，再減一天就是本月最後一天
        next_month = now.replace(day=28) + timedelta(days=4)
        this_month_end = (next_month - timedelta(days=next_month.day)).strftime('%Y-%m-%d')
        
        # 上個月
        last_month_end = (now.replace(day=1) - timedelta(days=1))
        last_month_start = last_month_end.replace(day=1).strftime('%Y-%m-%d')
        last_month_end_str = last_month_end.strftime('%Y-%m-%d')
        
        # 本週 (週一到週日)
        start_of_week = now - timedelta(days=now.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        this_week_start = start_of_week.strftime('%Y-%m-%d')
        this_week_end = end_of_week.strftime('%Y-%m-%d')

        schema_context = cls._load_schema_context()

        secure_key = SecretStr(api_key_str)
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0, api_key=secure_key)

        prompt = ChatPromptTemplate.from_messages([
            ("system", cls.SCHEMA_PROMPT_TEMPLATE),
            ("human", "問題：{query}")
        ])

        chain = prompt | llm
        try:
            # 🌟 將所有算好的動態時間注入 Prompt
            response = await chain.ainvoke({
                "today_str": today_str,
                "weekday_str": weekday_str,
                "this_month_start": this_month_start,
                "this_month_end": this_month_end,
                "last_month_start": last_month_start,
                "last_month_end": last_month_end_str,
                "this_week_start": this_week_start,
                "this_week_end": this_week_end,
                "this_year_start": this_year_start,
                "dynamic_schema": schema_context,
                "user_id": user_id,
                "query": user_query
            })

            raw_sql = str(response.content)
            final_sql = cls._self_correction(raw_sql, user_id)
            return final_sql
        except Exception as e:
            print(f"❌ SQL Generator 致命錯誤: {e}")
            return ""