import httpx
import asyncio
import os
async def test_anything_llm():
    # 1. 基礎設定
    base_url = "http://127.0.0.1:3001/v1/chat/completions" # 使用 IP 避免 localhost 解析問題
    api_key = os.getenv("ANYTHINGLLM_KEY") # ⚠️ 請在此處貼上你從 AnythingLLM 產生的 Key
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 2. 先測試身分驗證 (Auth Check)
    print("--- Step 1: Checking Auth ---")
    async with httpx.AsyncClient() as client:
        try:
            auth_res = await client.get(f"{base_url}/auth", headers=headers)
            print(f"Auth Status: {auth_res.status_code}")
            print(f"Auth Response: {auth_res.text}")
        except Exception as e:
            print(f"Auth Connection Failed: {str(e)}")
            return

    # 3. 測試聊天功能 (OpenAI Compatible API)
    # 注意：AnythingLLM 支援 OpenAI 格式，路徑通常是 /v1/chat/completions
    print("\n--- Step 2: Testing Chat ---")
    payload = {
        "model": "gemma3:1b", # 確保這跟你在 AnythingLLM 裡選的模型名稱一致
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, who are you?"}
        ]
    }

    async with httpx.AsyncClient() as client:
        try:
            # 修改端點為 OpenAI 相容路徑
            res = await client.post(
                "http://127.0.0.1:3001/v1/chat/completions", 
                json=payload, 
                headers=headers,
                timeout=30.0
            )
            print(f"Chat Status: {res.status_code}")
            if res.status_code == 200:
                print(f"Reply: {res.json()['choices'][0]['message']['content']}")
            else:
                print(f"Error: {res.text}")
        except Exception as e:
            print(f"Chat Failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_anything_llm())