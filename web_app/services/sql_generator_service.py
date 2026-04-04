# web_app/services/sql_generator_service.py
import os
import re
from datetime import datetime
from pydantic import SecretStr
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

class SQLGeneratorService:
    
    @classmethod
    def _load_schema_context(cls) -> str:
        """從資料夾讀取資料庫地圖 (Schema Collection)"""
        schema_path = "./web_app/data/manuals/schema_collection.md"
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
    今天的日期是 {today}。

    【重要時間指引】
    - 現在是 2026 年 4 月。
    - 如果問「上個月」，日期範圍是 2026-03-01 到 2026-03-31。
    - 如果問「今年以來」，範圍是 2026-01-01 到今天。
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
    3. 項目查詢：具體物品請用 `add_note LIKE '%關鍵字%'`。
    4. 時間範圍：本月為 `add_date BETWEEN {this_month_range}`。
    5. 會員隔離：必須包含 `user_id = {user_id}`。

    【🚨 轉帳查詢特別規定】
    - 如果使用者問的是「轉帳」，請務必檢查 {dynamic_schema} 中轉帳資料表的正確名稱與欄位！
    - 嚴禁把記帳表的 `add_date` 拿到轉帳表去用！(請使用轉帳表正確的日期與金額欄位)

    【⚠️ 搜尋鐵律】
    1. 必須包含 `WHERE user_id = {user_id}`。
    2. 收入 add_type=1, 支出 add_type=0。
    3. 日期篩選必須精確到天（BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'）。
    """

    @classmethod
    async def generate_sql(cls, user_query: str, user_id: int) -> str:
        api_key_str = os.getenv("GROQ_API_KEY")
        if not api_key_str: return ""

        now = datetime.now()
        this_month_start = now.replace(day=1).strftime('%Y-%m-%d')
        this_month_range = f"'{this_month_start}' AND '{now.strftime('%Y-%m-%d')}'"
        
        # 讀取地圖
        schema_context = cls._load_schema_context() # 變數名稱統一：schema_context

        secure_key = SecretStr(api_key_str)
        # 使用 70B 模型確保邏輯嚴密性
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0, api_key=secure_key)

        prompt = ChatPromptTemplate.from_messages([
            ("system", cls.SCHEMA_PROMPT_TEMPLATE),
            ("human", "問題：{query}")
        ])

        chain = prompt | llm
        try:
            # 傳入所有模板所需變數，名稱嚴格對齊
            response = await chain.ainvoke({
                "today": now.strftime("%Y-%m-%d"),
                "dynamic_schema": schema_context,
                "this_month_range": this_month_range,
                "user_id": user_id,
                "query": user_query
            })

            raw_sql = str(response.content)
            
            # 執行「反思機制」進行二次校正
            final_sql = cls._self_correction(raw_sql, user_id)
            
            return final_sql
        except Exception as e:
            print(f"❌ SQL Generator 致命錯誤: {e}")
            return ""