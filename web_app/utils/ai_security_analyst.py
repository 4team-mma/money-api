# web_app/utils/ai_security_analyst.py
import os
import logging
from ..services.ollama_service import OllamaService

logger = logging.getLogger(__name__)

async def run_daily_security_audit():
    logger.info("🛡️ [AI 資安分析] 開始執行每日資安日誌檢查...")
    log_path = "logs/security_audit.log"
    
    # 1. 檢查有沒有日誌檔案
    if not os.path.exists(log_path):
        logger.info("✅ 今日無異常連線紀錄，系統安全。")
        return

    # 2. 讀取日誌內容
    with open(log_path, "r", encoding="utf-8") as f:
        log_content = f.read().strip()

    if not log_content:
        logger.info("✅ 今日日誌為空，系統安全。")
        return

    # 若日誌太長，取最後 4000 字元避免 Token 爆表
    log_content = log_content[-4000:]

    # 3. 準備給 Gemma 4 的指令
    system_instruction = (
        "你是一個頂尖的網站資安防護 AI 專家。"
        "請分析以下的 Server 日誌（JSON 格式）。判斷是否有惡意掃描 (大量 404)、"
        "暴力破解密碼 (大量 401)、或異常爬蟲行為 (大量 429)。"
        "請用繁體中文輸出一份簡潔的【資安異常摘要報告】，並列出可疑的 IP。"
    )
    prompt = f"【今日系統異常日誌】：\n{log_content}"

    try:
        # 🌟 直接完美呼叫你寫好的 OllamaService！
        report = await OllamaService.chat_async(
            base_url="http://localhost:11434",
            model_id="gemma4:e4b",
            prompt=prompt,
            system_instruction=system_instruction
        )
        
        logger.info(f"🚨 [AI 資安報告結果]:\n{report}")
        
        # TODO: 未來你可以在這裡加上 send_discord_alert(report) 把報告傳到 Discord！

        # 4. 檢查完畢後清空日誌，準備迎接明天的紀錄
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("")
            
    except Exception as e:
        logger.error(f"❌ AI 資安分析執行失敗: {e}")