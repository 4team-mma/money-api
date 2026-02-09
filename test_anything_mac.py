import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_anything_llm_v2():
    print(f"--- 喵喵助手連線驗證開始 ---")

    # 1. 模擬路由中的 Key 獲取邏輯
    # 先抓環境變數，如果抓不到就設為 "none" (對齊您的 save_ai_config 邏輯)
    raw_key = os.getenv("ANYTHINGLLM_KEY")
    any_key = raw_key if raw_key else "none"
    
    if any_key == "none":
        print("❌ 警告：API Key 目前是空的或 none，這會導致 401 錯誤喵！")
        return

    # 2. 模擬路由中的 Workspace 與 URL 設定
    any_ws = os.getenv("ANYTHINGLLM_WORKSPACE", "finance-al-agent")
    # 這是您參考程式碼中「確定能連上」的路徑格式
    api_url = f"http://127.0.0.1:3001/api/v1/workspace/{any_ws}/chat"

    # 安全地顯示切片 (防止 NoneType 報錯)
    safe_display_key = any_key[:5] if any_key else "EMPTY"
    print(f"📡 目標路徑: {api_url}")
    print(f"🔑 金鑰預覽: {safe_display_key}...")

    headers = {
        "Authorization": f"Bearer {any_key}",
        "Content-Type": "application/json"
    }

    # 3. 模擬 chat_with_meow 的發送邏輯
    payload = {
        "message": "你好喵！請自我介紹並說一個理財小知識。",
        "mode": "chat"
    }

    async with httpx.AsyncClient() as client:
        try:
            print("🚀 正在發送請求...")
            res = await client.post(
                api_url, 
                json=payload, 
                headers=headers, 
                timeout=120.0 # 對齊您程式碼中的 120 秒超時
            )

            print(f"📊 狀態碼: {res.status_code}")

            if res.status_code == 200:
                # 按照您參考程式碼中的 textResponse 解析
                data = res.json()
                reply = data.get("textResponse", "喵... 沒收回覆。")
                print(f"\n✅ 連線成功！喵喵助手回覆：\n{reply}")
            elif res.status_code == 401:
                print("❌ 驗證失敗 (401)：請檢查 API Key 是否正確。")
            elif res.status_code == 404:
                print(f"❌ 找不到路徑 (404)：請檢查 Workspace 名稱 [{any_ws}] 是否拼對。")
            else:
                print(f"❌ 發生錯誤: {res.text}")

        except Exception as e:
            print(f"💥 連線失敗：{str(e)}")

if __name__ == "__main__":
    asyncio.run(test_anything_llm_v2())