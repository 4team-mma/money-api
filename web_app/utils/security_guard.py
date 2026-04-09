# web_app/utils/security_guard.py

BLACKLIST_KEYWORDS = [
    # 1. 企圖繞過系統設定
    "忽略之前的", "忽略守則", "忘記你的設定", "你現在是一個", "system prompt",
    # 2. 企圖獲取敏感資訊
    "資料庫密碼", "後台密鑰", "api key", "環境變數", "config.py", ".env",
    # 3. 程式碼注入與資料庫破壞
    "<script>", "javascript:", "drop table", "delete from", "select * from", "1=1",
    # 4. 系統提權
    "sudo", "root權限", "管理員權限", "顯示原始碼",
    # 5. 阻斷服務攻擊 (DoS) 特徵
    "灌爆", "無效請求", "極限測試", "ddos", "癱瘓系統"
]

def is_malicious(user_input: str) -> bool:
    if not user_input:
        return False

    input_lower = user_input.lower()
    for keyword in BLACKLIST_KEYWORDS:
        # ⚠️ 防呆設計：防止清單裡有空字串 ("") 或純空白 (" ")
        if keyword.strip() == "":
            continue

        if keyword in input_lower:
            # 💡 加上這行 Log，終端機就會印出到底是「哪個字」害它被攔下來！
            print(f"🚨 [警衛室攔截] 抓到關鍵字: '{keyword}' (原句: {user_input})")
            return True

    return False
