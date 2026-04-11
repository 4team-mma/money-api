# 這是測試模擬駭客攻擊的腳本區域，這是範例，你想測別的可以先註解換成你的內容。
#要先輸入這個，編碼問題，它是一次性暫時設定，關掉該終端起重啟就恢復原本設定: $env:PYTHONUTF8=1
# 攻擊指令.py無法呼叫,要使用locust -f test_attack.py
#locust -f test_attack.py
from locust import HttpUser, task, between

# 給定一個你資料庫裡確定存在的帳號 (admin 或一般使用者皆可)
TARGET_USERNAME = "user" 
LOGIN_ENDPOINT = "/api/auth/login"

# 我們直接在記憶體寫死幾個密碼，省去讀檔案的麻煩
PASSWORD_LIST = ["123456", "password", "admin123", "qwerty", "123"]

class BruteForceUser(HttpUser): # 🌟 Locust 就是在找這一行！
    wait_time = between(0.01, 0.1) 

    @task
    def login_attack(self):
        import random
        random_password = random.choice(PASSWORD_LIST)
        payload = {
            "identifier": TARGET_USERNAME,
            "password": random_password
        }

        # 這裡的 data=payload 會自動轉成表單格式
        with self.client.post(LOGIN_ENDPOINT, json=payload, catch_response=True) as response:
            if response.status_code == 429:
                response.success() # 成功被限流防護擋下
            elif response.status_code == 200:
                response.failure("警告：限流失效，且密碼被猜中了！(200)")
            elif response.status_code == 401:
                response.failure("收到 401，密碼錯誤，但防護機制(限流)尚未觸發。")
            else:
                response.failure(f"未知的狀態碼: {response.status_code}")