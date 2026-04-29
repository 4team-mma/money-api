# web_app/services/notion_mcp_service.py
import os
import sys  
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy.orm import Session
from ..models import Member
import json

logger = logging.getLogger(__name__)

# 🌟 完整複製系統環境變數，確保 Windows / Mac 都不會因為缺變數當機
safe_env = os.environ.copy()
safe_env.update({
    "NOTION_API_TOKEN": str(os.getenv("NOTION_API_TOKEN", "")),
    "NOTION_API_KEY": str(os.getenv("NOTION_API_TOKEN", ""))
})

# 🌟 自動判斷系統，Windows 用 npx.cmd，Mac 用 npx
npx_command = "npx.cmd" if sys.platform == "win32" else "npx"

server_params = StdioServerParameters(
    command=npx_command,
    args=["-y", "@ramidecodes/mcp-server-notion@latest"],
    env=safe_env
)

def create_notion_tool(db: Session, user: Member):
    """
    閉包工廠：把 db 和 user 鎖進去，讓 AI 呼叫時能查真實資料
    跟 advisor_graph_service.py 的 tool 模式完全一樣
    """
    
    async def add_expense_to_notion(category: str = "飲食", time_frame: str = "本月", **kwargs) -> str:
        """
        將使用者的財務花費摘要寫入 Notion 資料庫。
        觸發時機：當使用者提出「寫入 Notion」、「記錄到 Notion」或「同步」等明確要求時，請務必呼叫此工具取得真實數據。
        category 參數：要分析的消費類別，例如「飲食」、「交通」、「娛樂」，預設為「飲食」。
        time_frame 參數：使用者想查詢的時間範圍，請根據對話判斷填入「本月」或「上個月」，預設為「本月」。
        """
        
        # 🌟 把這行加進來，讓 Pylance 知道 notion_token 是哪來的！
        notion_token = os.getenv("NOTION_API_TOKEN") or os.getenv("NOTION_API_KEY")
        # 若連金鑰都沒有，直接擋下來
        if not notion_token:
            return "❌ 系統錯誤：找不到 Notion API 金鑰，請檢查系統後台的 .env 檔案！"

        page_id = "3507efad061f80578aa3caf6d2ff21d7"

        try:
            from datetime import date, timedelta
            from sqlalchemy import func
            from ..models import AddRecord, Account

            today = date.today()

            # ==========================================
            # 🌟 核心：根據 AI 傳來的時間，動態計算日期區間
            # ==========================================
            if time_frame == "上個月":
                # 目標月：上個月
                target_end = today.replace(day=1) - timedelta(days=1)
                target_start = target_end.replace(day=1)
                # 比較月：上上個月 (用來算 ↑↓ 比例)
                prev_end = target_start - timedelta(days=1)
                prev_start = prev_end.replace(day=1)
                period_name = "上月"
                prev_period_name = "上上月"
            else:
                # 目標月：本月
                target_start = today.replace(day=1)
                target_end = today
                # 比較月：上個月
                prev_end = target_start - timedelta(days=1)
                prev_start = prev_end.replace(day=1)
                period_name = "本月"
                prev_period_name = "上月"

            # 查指定類別目標月支出
            cat_expense = (
                db.query(func.sum(AddRecord.add_amount))
                .filter(
                    AddRecord.user_id == user.user_id,
                    AddRecord.add_type == False,
                    AddRecord.add_class == category,
                    AddRecord.add_date >= target_start,
                    AddRecord.add_date <= target_end, # 🌟 加上結束時間限制
                )
                .scalar() or 0
            )

            # 查目標月總支出
            total_expense = (
                db.query(func.sum(AddRecord.add_amount))
                .filter(
                    AddRecord.user_id == user.user_id,
                    AddRecord.add_type == False,
                    AddRecord.add_date >= target_start,
                    AddRecord.add_date <= target_end,
                )
                .scalar() or 0
            )

            # 查目標月總收入
            total_income = (
                db.query(func.sum(AddRecord.add_amount))
                .filter(
                    AddRecord.user_id == user.user_id,
                    AddRecord.add_type == True,
                    AddRecord.add_date >= target_start,
                    AddRecord.add_date <= target_end,
                )
                .scalar() or 0
            )

            # 查淨資產 (淨資產看的是「當下」，所以不限月份)
            accounts = db.query(Account).filter(
                Account.user_id == user.user_id,
                Account.exclude_from_assets == False
            ).all()
            net_worth = sum(float(a.current_balance) for a in accounts)

            ratio = round(float(cat_expense) / float(total_expense) * 100, 1) if total_expense > 0 else 0

            # 查「比較月」的同類別支出
            last_cat = (
                db.query(func.sum(AddRecord.add_amount))
                .filter(
                    AddRecord.user_id == user.user_id,
                    AddRecord.add_type == False,
                    AddRecord.add_class == category,
                    AddRecord.add_date >= prev_start,
                    AddRecord.add_date <= prev_end,
                )
                .scalar() or 0
            )
            change = round((float(cat_expense) - float(last_cat)) / float(last_cat) * 100, 1) if last_cat > 0 else 0
            change_text = f"↑{change}%" if change > 0 else f"↓{abs(change)}%"

            # ── 替換字眼，讓摘要看起來正確 ────────────────────────
            summary = (
                f"📊 {target_start.strftime('%Y/%m')} {user.name} 財務摘要\n\n"
                f"【{category}花費分析】\n"
                f"• {period_name}{category}支出：NT$ {int(cat_expense):,}\n"
                f"• 佔{period_name}總支出比例：{ratio}%\n"
                f"• 與{prev_period_name}相比：{change_text}（{prev_period_name} NT$ {int(last_cat):,}）\n\n"
                f"【{period_name}總覽】\n"
                f"• 總收入：NT$ {int(total_income):,}\n"
                f"• 總支出：NT$ {int(total_expense):,}\n"
                f"• 結餘：NT$ {int(total_income - total_expense):,}\n"
                f"• 當前淨資產：NT$ {int(net_worth):,}\n\n"
                f"📅 記錄時間：{today.strftime('%Y-%m-%d')}"
            )

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

            logger.info(f"✅ [Notion] {period_name} {category} 財務摘要寫入成功")
            
            # 回傳給 AI 的提示詞也要跟著動態更新
            return (
                f"【系統提示：資料已成功寫入 Notion！】\n"
                f"請務必根據此結果，用充滿活力與親切的語氣，向小主人報告這個好消息。\n"
                f"例如你可以說：『喵！已經幫小主人把【{period_name}】的【{category}花費】整理好，並寫入 Notion 囉！』\n"
                f"絕對不要只問『還需要什麼幫忙』，一定要明確說出你剛剛完成了什麼任務喵！\n\n"
                f"以下是寫入的數據供你參考（不一定要全唸出來）：\n{summary}"
            )

        except Exception as e:
            logger.error("❌ [Notion] 寫入失敗", exc_info=True)
            return f"寫入 Notion 失敗了喵：{str(e)}"

    return add_expense_to_notion