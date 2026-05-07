# web_app/services/notion_mcp_service.py
import os
import sys  
import logging
import json
import re
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy.orm import Session
from ..models import Member
from ..utils.ai_security import decrypt_api_key

logger = logging.getLogger(__name__)

safe_env_template = os.environ.copy()
npx_command = "npx.cmd" if sys.platform == "win32" else "npx"

def create_notion_tool(db: Session, user: Member):
    
    async def add_expense_to_notion(category: str = "飲食", time_frame: str = "本月") -> str:
        """
        將使用者的財務花費寫入 Notion。
        觸發時機：當使用者提出「寫入 Notion」、「記錄到 Notion」時。
        
        :param category: 消費類別，例如「飲食」、「交通」，預設為「飲食」。
        :param time_frame: 時間範圍，只能嚴格填入「本月」或「上個月」，絕對不要產生其他格式。
        """
        
        raw_token = user.notion_api_key       
        raw_page_id = str(user.notion_page_id).strip()

        if not raw_token or not raw_page_id:
            return "❌ 你還沒有綁定 Notion 喵！請先到帳號設定頁面填入 API Key 和 Page ID。"

        # ==========================================
        # 🌟 修正 1：自動從完整網址中萃取 32 碼純 ID
        # 避免使用者貼上整段 https://... 導致 API 找不到頁面
        # ==========================================
        match = re.search(r'([a-fA-F0-9]{32})', raw_page_id.replace('-', ''))
        if match:
            page_id = match.group(1)
        else:
            return "❌ Notion Page ID 格式錯誤，請確保裡面包含 32 碼的字母數字組合喵！"

        # Token 防呆解密
        raw_token_str = str(raw_token).strip()
        if raw_token_str.startswith("secret_") or raw_token_str.startswith("ntn_"):
            notion_token = raw_token_str
        else:
            notion_token = decrypt_api_key(raw_token_str)
        
        if not notion_token or not (notion_token.startswith("secret_") or notion_token.startswith("ntn_")):
            return "❌ Notion 憑證無效或解密失敗，請檢查資料庫中儲存的 API Key 格式喵！"

        try:
            from datetime import date, timedelta
            from sqlalchemy import func
            from ..models import AddRecord, Account

            today = date.today()

            # ==========================================
            # 🌟 修正 2：強健的「上個月」判斷
            # 兼容 AI 回傳 "2026-04" 或把條件塞在 kwargs 裡的情況
            # ==========================================
            is_last_month = False
            if time_frame in ["上個月", "上月"]:
                is_last_month = True

            if is_last_month:
                target_end = today.replace(day=1) - timedelta(days=1)
                target_start = target_end.replace(day=1)
                prev_end = target_start - timedelta(days=1)
                prev_start = prev_end.replace(day=1)
                period_name, prev_period_name = "上月", "上上月"
            else:
                target_start = today.replace(day=1)
                target_end = today
                prev_end = target_start - timedelta(days=1)
                prev_start = prev_end.replace(day=1)
                period_name, prev_period_name = "本月", "上月"

            # --- 資料庫查詢邏輯 (保持不變) ---
            cat_expense = db.query(func.sum(AddRecord.add_amount)).filter(
                AddRecord.user_id == user.user_id, AddRecord.add_type == False,
                AddRecord.add_class == category, AddRecord.add_date >= target_start, AddRecord.add_date <= target_end
            ).scalar() or 0

            total_expense = db.query(func.sum(AddRecord.add_amount)).filter(
                AddRecord.user_id == user.user_id, AddRecord.add_type == False,
                AddRecord.add_date >= target_start, AddRecord.add_date <= target_end
            ).scalar() or 0

            total_income = db.query(func.sum(AddRecord.add_amount)).filter(
                AddRecord.user_id == user.user_id, AddRecord.add_type == True,
                AddRecord.add_date >= target_start, AddRecord.add_date <= target_end
            ).scalar() or 0

            accounts = db.query(Account).filter(Account.user_id == user.user_id, Account.exclude_from_assets == False).all()
            net_worth = sum(float(a.current_balance) for a in accounts)
            ratio = round(float(cat_expense) / float(total_expense) * 100, 1) if total_expense > 0 else 0
            last_cat = db.query(func.sum(AddRecord.add_amount)).filter(
                AddRecord.user_id == user.user_id, AddRecord.add_type == False,
                AddRecord.add_class == category, AddRecord.add_date >= prev_start, AddRecord.add_date <= prev_end
            ).scalar() or 0
            change = round((float(cat_expense) - float(last_cat)) / float(last_cat) * 100, 1) if last_cat > 0 else 0
            change_text = f"↑{change}%" if change > 0 else f"↓{abs(change)}%"

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

            user_env = safe_env_template.copy()
            user_env["NOTION_API_TOKEN"] = notion_token
            user_env["NOTION_API_KEY"] = notion_token

            user_server_params = StdioServerParameters(
                command=npx_command,
                args=["--yes", "--quiet", "@ramidecodes/mcp-server-notion@latest"],
                env=user_env
            )

            blocks_list = [
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
            ]
            blocks_json_string = json.dumps(blocks_list)

            # 啟動 MCP Client 並呼叫工具
            async with stdio_client(user_server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    
                    result = await session.call_tool("append-blocks", {
                        "block_id": page_id,
                        "children": blocks_json_string
                    })

                    # ==========================================
                    # 🌟 修正 3：嚴格檢查 MCP 是否回傳邏輯錯誤
                    # 攔截 Notion 權限不足或頁面找不到的狀況
                    # ==========================================
                    if getattr(result, 'isError', False):
                        error_msg = getattr(result.content[0], 'text', str(result.content[0])) if result.content else "未知錯誤"
                        logger.error(f"❌ [Notion] 寫入被拒絕: {error_msg}")
                        return (
                            f"❌ 呼叫 Notion 失敗了喵！Notion 回報錯誤：\n`{error_msg}`\n\n"
                            f"💡 小提醒：請確保你有在 Notion 頁面右上角的 `...` 選單中，點擊 `Connect (加入連結)` 並選擇你的 MoneyMMA 機器人喔！"
                        )

            logger.info(f"✅ [Notion] {period_name} {category} 寫入成功 (User: {user.name}, Page: {page_id})")
            
            # 🌟 加上強烈的系統約束，防止 LLM 偷懶只回「喵～」
            return (
                f"【系統強制執行指令：動作已完成，你必須直接向使用者報告】\n"
                f"狀態：已將【{period_name}】【{category}】財務摘要成功寫入 Notion。\n"
                f"約束：請嚴格遵照以下格式回答使用者，絕對不准只回答單一字詞或只有「喵」：\n\n"
                f"「報告小主人！已經幫您把【{period_name}】的【{category}花費】整理好，並同步到 Notion 頁面最下方囉喵！本月結餘是 {int(total_income - total_expense)} 元！」"
            )

        except Exception as e:
            logger.error("❌ [Notion] 執行發生異常", exc_info=True)
            return f"發生系統異常了喵：{str(e)}"

    return add_expense_to_notion