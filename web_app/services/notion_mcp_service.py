# web_app/services/notion_mcp_service.py
import os
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy.orm import Session
from ..models import Member
import json

logger = logging.getLogger(__name__)

safe_env = {
    "NOTION_API_TOKEN": str(os.getenv("NOTION_API_TOKEN", "")),
    "NOTION_API_KEY": str(os.getenv("NOTION_API_TOKEN", "")),
    "PATH": str(os.getenv("PATH", ""))
}

server_params = StdioServerParameters(
    command="npx",
    args=["-y", "@ramidecodes/mcp-server-notion@latest"],
    env=safe_env
)


def create_notion_tool(db: Session, user: Member):
    """
    閉包工廠：把 db 和 user 鎖進去，讓 Gemini 呼叫時能查真實資料
    跟 advisor_graph_service.py 的 tool 模式完全一樣
    """
    
    async def add_expense_to_notion(category: str = "飲食") -> str:
        """
        查詢指定類別的本月真實花費數據，組成財務摘要後寫入 Notion。
        當使用者要求「寫入 Notion」、「同步到 Notion」、「記錄到 Notion」時使用。
        category 參數：要分析的消費類別，例如「飲食」、「交通」、「娛樂」，預設為「飲食」
        """
        page_id = "3507efad061f80578aa3caf6d2ff21d7"

        try:
            # ── 第一步：查真實資料庫 ────────────────────────────────
            from datetime import date, timedelta
            from sqlalchemy import func, extract
            from ..models import AddRecord, Account

            today = date.today()
            month_start = today.replace(day=1)

            # 查指定類別本月支出
            cat_expense = (
                db.query(func.sum(AddRecord.add_amount))
                .filter(
                    AddRecord.user_id == user.user_id,
                    AddRecord.add_type == False,
                    AddRecord.add_class == category,
                    AddRecord.add_date >= month_start,
                )
                .scalar() or 0
            )

            # 查本月總支出
            total_expense = (
                db.query(func.sum(AddRecord.add_amount))
                .filter(
                    AddRecord.user_id == user.user_id,
                    AddRecord.add_type == False,
                    AddRecord.add_date >= month_start,
                )
                .scalar() or 0
            )

            # 查本月總收入
            total_income = (
                db.query(func.sum(AddRecord.add_amount))
                .filter(
                    AddRecord.user_id == user.user_id,
                    AddRecord.add_type == True,
                    AddRecord.add_date >= month_start,
                )
                .scalar() or 0
            )

            # 查淨資產
            accounts = db.query(Account).filter(
                Account.user_id == user.user_id,
                Account.exclude_from_assets == False
            ).all()
            net_worth = sum(float(a.current_balance) for a in accounts)

            # 計算佔比
            ratio = round(float(cat_expense) / float(total_expense) * 100, 1) if total_expense > 0 else 0

            # 查上個月同類別
            last_month_end = month_start - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            last_cat = (
                db.query(func.sum(AddRecord.add_amount))
                .filter(
                    AddRecord.user_id == user.user_id,
                    AddRecord.add_type == False,
                    AddRecord.add_class == category,
                    AddRecord.add_date >= last_month_start,
                    AddRecord.add_date <= last_month_end,
                )
                .scalar() or 0
            )
            change = round((float(cat_expense) - float(last_cat)) / float(last_cat) * 100, 1) if last_cat > 0 else 0
            change_text = f"↑{change}%" if change > 0 else f"↓{abs(change)}%"

            # ── 第二步：組成有意義的摘要文字 ────────────────────────
            summary = (
                f"📊 {today.strftime('%Y/%m')} {user.name} 財務摘要\n\n"
                f"【{category}花費分析】\n"
                f"• 本月{category}支出：NT$ {int(cat_expense):,}\n"
                f"• 佔本月總支出比例：{ratio}%\n"
                f"• 與上月相比：{change_text}（上月 NT$ {int(last_cat):,}）\n\n"
                f"【本月總覽】\n"
                f"• 總收入：NT$ {int(total_income):,}\n"
                f"• 總支出：NT$ {int(total_expense):,}\n"
                f"• 結餘：NT$ {int(total_income - total_expense):,}\n"
                f"• 當前淨資產：NT$ {int(net_worth):,}\n\n"
                f"📅 記錄時間：{today.strftime('%Y-%m-%d')}"
            )

            # ── 第三步：寫入 Notion ─────────────────────────────────
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    blocks_data = json.dumps([
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{
                                    "type": "text",
                                    "text": {"content": summary}
                                }]
                            }
                        }
                    ])

                    await session.call_tool("append-blocks", {
                        "block_id": page_id,
                        "children": blocks_data
                    })

            logger.info(f"✅ [Notion] {category} 財務摘要寫入成功")
            return f"✅ 已將真實的{category}財務數據摘要寫入 Notion 喵！\n\n{summary}"

        except Exception as e:
            logger.error("❌ [Notion] 寫入失敗", exc_info=True)
            return f"寫入 Notion 失敗了喵：{str(e)}"

    return add_expense_to_notion