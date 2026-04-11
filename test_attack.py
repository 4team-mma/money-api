# 這是測試模擬駭客攻擊的腳本區域，這是範例，你想測別的可以先註解換成你的內容。
#要先輸入這個，編碼問題，它是一次性暫時設定，關掉該終端起重啟就恢復原本設定: $env:PYTHONUTF8=1
# 攻擊指令.py無法呼叫,要使用locust -f test_attack.py
#locust -f test_attack.py
import random
import string
from locust import HttpUser, task, between

TARGET_USERNAME = "user" 
LOGIN_ENDPOINT = "/api/auth/login"

# --- 1. 讀取字典檔 ---
PASSWORD_LIST = []
try:
    with open("passwords.txt", "r", encoding="utf-8") as f:
        PASSWORD_LIST = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    PASSWORD_LIST = ["123456", "password", "admin123"]

# --- 2. 🌟 建立智慧密碼產生器 (Generator) ---
def get_next_password():
    """
    這是一個產生器。
    階段一：不重複地發送字典檔裡的所有密碼。
    階段二：字典耗盡後，無限產生隨機英數組合。
    """
    # 階段一：字典攻擊 (絕不重複)
    for pwd in PASSWORD_LIST:
        yield pwd
    
    # 階段二：純暴力破解 (無限隨機產生)
    print("\n⚠️ 警告：字典檔已耗盡！切換至 [純隨機暴力破解模式]...\n")
    while True:
        # 隨機產生 6~8 位的英數組合 (例如: aB3x9Q)
        length = random.randint(6, 8)
        random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=length))
        yield random_str

# 初始化一個全域的產生器 (讓所有蝗蟲大軍共用同一個發牌官)
password_generator = get_next_password()

# --- 3. 定義駭客行為 ---
class BruteForceUser(HttpUser): 
    wait_time = between(0.01, 0.1) 

    @task
    def login_attack(self):
        # 🌟 每次攻擊都向發牌官拿「下一組」密碼，保證前段不重複
        current_password = next(password_generator)
        
        payload = {
            "identifier": TARGET_USERNAME,
            "password": current_password
        }

        with self.client.post(LOGIN_ENDPOINT, json=payload, catch_response=True) as response:
            if response.status_code == 429:
                response.success() # 成功被限流防護擋下
            elif response.status_code == 200:
                # 🌟 這裡會把猜中的密碼顯示在 Locust 的 Failures 列表中！
                response.failure(f"🚨 警告：防護失效，密碼被猜中了！帳號: {TARGET_USERNAME} / 密碼: [{current_password}]")
            elif response.status_code == 401:
                response.failure("收到 401，密碼錯誤，防護機制(限流)尚未觸發。")
            else:
                response.failure(f"未知的狀態碼: {response.status_code}")