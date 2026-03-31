import os
import asyncio
from dotenv import load_dotenv
from google import genai

load_dotenv()

async def list_available_models():
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ 錯誤：找不到 API_KEY，請檢查 .env 檔案")
        return

    client = genai.Client(api_key=api_key)
    
    try:
        print(f"🔍 正在獲取模型列表...")
        # 直接獲取模型清單
        models = client.models.list()
        
        print("\n✅ 你的 Key 目前可用的模型 ID 清單如下：")
        print("-" * 60)
        
        count = 0
        for model in models:
            # 這裡我們不檢查屬性，直接印出 name
            # 正常來說，這些模型名稱會長得像 "gemini-3-flash-preview"
            print(f"📌 {model.name}")
            count += 1
            
        print("-" * 60)
        print(f"共計發現 {count} 個可用模型。")
        
    except Exception as e:
        print(f"❌ 無法獲取模型列表，這通常代表 API Key 無效或網路被封鎖：")
        print(f"錯誤原因：{str(e)}")

if __name__ == "__main__":
    asyncio.run(list_available_models())