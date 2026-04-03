# test_brain.py (絕對路徑版)
import sys
import os

# 1. 取得這支檔案所在目錄的絕對路徑 (專案根目錄)
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 2. 嘗試匯入模組 (移除開頭的點，因為已經把 root 加入 sys.path)
try:
    from web_app.routes.ai.ai_cat_test import arena_brains
    print("✅ 擂台大腦模組導入成功！")
except ImportError as e:
    print(f"❌ 導入失敗！錯誤原因: {e}")
    print(f"請檢查 web_app 內是否有 __init__.py 檔案")
    sys.exit(1)

# 3. 執行測試文字
test_text = "今天天氣真好"
print(f"\n[測試開始] 語句：{test_text}")
print("-" * 40)
# 在 test_brain.py 呼叫預測之前加入
words = ["今天", "天氣", "真", "好"]
vocab = arena_brains.v2_vocab
print(f"DEBUG - 斷詞編號 check: {[vocab.get(w, '找不到') for w in words]}")

# V1 預測
v1_intent, v1_conf = arena_brains.predict_v1(test_text)
print(f"🤖 V1 預測：{v1_intent} ({v1_conf*100:.1f}%)")

# V2 預測
v2_intent, v2_conf, v2_intercepted = arena_brains.predict_v2(test_text)
print(f"🚀 V2 預測：{v2_intent} ({v2_conf*100:.1f}%) {'[🛡️ 攔截]' if v2_intercepted else ''}")

# 印出當前 V2 使用的標籤地圖順序，確認是否為 A-Z
print("-" * 40)
print(f"📍 當前標籤地圖 (應為 A-Z): \n{arena_brains.v2_labels}")
