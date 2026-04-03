import os
import re
from datetime import datetime, timedelta, date
from pydantic import SecretStr
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

class SQLGeneratorService:
    # 🌟 完整資料庫 Schema，包含所有 18 個表格
    SCHEMA_PROMPT = """
    你是一個專業的 MySQL 專家。請根據以下完整的表結構生成正確的 SQL。
    今天的日期是 {today}。
    - 問：「上個月(3月)總收入？」
    答：SELECT SUM(add_amount) FROM adds WHERE user_id = {user_id} AND add_type = 1 AND add_date BETWEEN '2026-03-01' AND '2026-03-31';
    - 問：「上個月支出？」
    答：SELECT SUM(add_amount) FROM adds WHERE user_id = {user_id} AND add_type = 0 AND add_date BETWEEN '2026-03-01' AND '2026-03-31';

    1. 表 `members`: user_id, email, username, xp, level, points
    2. 表 `accounts`: account_id, user_id, account_type, account_name, current_balance
    3. 表 `notifications`: user_id, reminder_title, reminder_date_start, repeat_cycle
    4. 表 `adds` (主要收支表): add_id, user_id, add_date, add_amount, add_type(1收, 0支), add_class, add_note, account_id, add_tag
    5. 表 `transactions` (轉帳表): transaction_id, user_id, transaction_date, from_account_id, to_account_id, amount
    6. 表 `password_resets`: user_id, otp_code, expires_at
    7. 表 `feedbacks`: user_id, feedback_name, question_type, content
    8. 表 `cpi_data`: category, period, val
    9. 表 `salary_benchmarks`: industry, period, salary_val
    10. 表 `settings`: user_id, budget_cycle, app_theme
    11. 表 `ai_configs`: user_id, provider, model_version
    12. 表 `checkin`: user_id, checkin_date, streak_count, total_checkins
    13. 表 `misscards_library`: lib_id, type, title, difficulty, description
    14. 表 `daily_missions`: user_id, lib_id, miss_status, current_val
    15. 表 `ach_cards`: user_id, lib_id, is_unlocked
    16. 表 `budgets`: user_id, amount, category, tag
    17. 表 `savings_goals`: user_id, goal_name, target_amount, current_amount
    18. 表 `login_activities`: user_id, ip_address, device_info, login_at

    【⚠️ 搜尋鐵律 - 絕對遵循】:
    1. **收支判定**:
       - 提到「花了、支出、消費、花費」，必須針對 `adds` 表加上 `add_type = 0`。
       - 提到「賺了、收入、薪水、領錢」，必須針對 `adds` 表加上 `add_type = 1`。
    2. **類別 vs 具體項目 (重要！)**:
       - 提到「飲食、交通、居家、購物、娛樂、醫療、教育、投資、人情、其他」，請對準 `add_class` 欄位。
       - 提到具體物品名稱（如：包子、捷運、漢堡、iPhone、房租），必須使用 `add_note LIKE '%名稱%'`。
    3. **轉帳判定**:
       - 若提到「轉帳、戶轉、從 A 帳戶搬到 B 帳戶」，請查詢 `transactions` 表。
    4. **時間範圍 (使用動態日期)**:
       - 「上個月」: 必須精準使用 `add_date BETWEEN {last_month_range}`。
       - 「本月」: 必須精準使用 `add_date BETWEEN {this_month_range}`。
       - 「這週」: 必須使用 `add_date >= {this_week_start}`。
    5. **安全門禁**: 必須包含 `WHERE user_id = {user_id}`。
    6. **輸出格式**: 僅輸出純 SQL 語句，禁止 Markdown 或解釋，禁止在欄位名稱（如 add_type）中間加空格。
    """

    @classmethod
    async def generate_sql(cls, user_query: str, user_id: int) -> str:
        api_key_str = os.getenv("GROQ_API_KEY")
        if not api_key_str: return ""

        # --- 🚀 動態日期計算 ---
        now = datetime.now()
        this_month_start = now.replace(day=1).strftime('%Y-%m-%d')
        this_month_range = f"'{this_month_start}' AND '{now.strftime('%Y-%m-%d')}'"

        last_day_prev_month = now.replace(day=1) - timedelta(days=1)
        first_day_prev_month = last_day_prev_month.replace(day=1).strftime('%Y-%m-%d')
        last_month_range = f"'{first_day_prev_month}' AND '{last_day_prev_month.strftime('%Y-%m-%d')}'"

        this_week_start = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')

        secure_key = SecretStr(api_key_str)
        # 使用 70B 模型生成 SQL，精準度最高
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0, api_key=secure_key)

        prompt = ChatPromptTemplate.from_messages([
            ("system", cls.SCHEMA_PROMPT),
            ("human", "小主人問：{query}")
        ])

        chain = prompt | llm
        try:
            response = await chain.ainvoke({
                "user_id": user_id,
                "today": now.strftime("%Y-%m-%d"),
                "last_month_range": last_month_range,
                "this_month_range": this_month_range,
                "this_week_start": f"'{this_week_start}'",
                "query": user_query
            })

            # 🚀 核心修正：使用正則表達式清理換行與多餘空格，防止語句破碎
            sql_text = re.sub(r'\s+', ' ', str(response.content)).strip()
            sql_text = sql_text.replace("```sql", "").replace("```", "").strip()

            # 🛡️ 二次防呆：修正常見的欄位名稱空格錯誤
            sql_text = sql_text.replace("add_ _", "add_").replace("add_ _type", "add_type").replace("add_ _class", "add_class")

            # 安全強制檢查 user_id 隔離
            if f"user_id = {user_id}" not in sql_text and f"user_id={user_id}" not in sql_text.replace(" ", ""):
                if "WHERE" in sql_text.upper():
                    sql_text = sql_text.replace("WHERE", f"WHERE user_id = {user_id} AND")
                else:
                    sql_text += f" WHERE user_id = {user_id}"

            return sql_text
        except Exception:
            return ""
