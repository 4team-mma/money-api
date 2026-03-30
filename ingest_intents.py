# python ingest_intents.py
import os
import pandas as pd
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEndpointEmbeddings
import chromadb

load_dotenv()

# 檔案路徑設定
# ==========================================
# 🌟 跨平台無敵寫法：讓 Python 動態找路徑
# ==========================================
# 1. 必須先定義 BASE_DIR (抓到目前這支檔案所在的絕對資料夾路徑)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEST_DATA_FILE = os.path.join(BASE_DIR, "web_app", "temp", "excel", "golden_test.xlsx")
CHROMA_PERSIST_DIR = os.path.join(BASE_DIR, ".chromadb")


def ingest_intents():
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        print("❌ 請先在 .env 檔案中設定 HF_TOKEN")
        return

    # 1. 讀取你的黃金測試集 (作為警衛室的防呆範本)
    if not os.path.exists(TEST_DATA_FILE):
        print(f"❌ 找不到測試集檔案: {TEST_DATA_FILE}")
        return
        
    print(f"📊 正在讀取意圖黃金測試集: {TEST_DATA_FILE}")
    df = pd.read_excel(TEST_DATA_FILE) # 如果你是 xlsx，請改成 pd.read_excel(TEST_DATA_FILE)
    
    # 確保不會讀到空值
    df = df.dropna(subset=['text', 'intent'])
    
    # 將 DataFrame 轉成 langchain_chroma 需要的格式
    texts = df['text'].astype(str).tolist()
    # 把意圖存成 metadata，這樣比對出來時才知道是什麼意圖
    metadatas = [{"intent": str(intent)} for intent in df['intent'].tolist()]
    
    print(f"🔍 總共載入 {len(texts)} 筆意圖範例！")

    # 2. 清除舊的警衛室房間 (確保意圖更新時不會重複疊加)
    if os.path.exists(CHROMA_PERSIST_DIR):
        print("🧹 準備清理舊的意圖資料庫...")
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        try:
            # 只刪除 1樓 (intent_examples)，不會動到 2樓 (system_manual)
            client.delete_collection("intent_examples")
            print("✅ 已清空舊的意圖資料庫！")
        except Exception:  # 🌟 關鍵修正：改成 Exception，不管發生什麼找不到的錯都忽略！
            print("💡 1樓警衛室目前還是空的，我們直接開始動工建立！")
            pass

    # 3. 準備向量化引擎 (解決你看到的 embeddings 紅線問題)
    print("🧠 正在啟動 HuggingFace 向量化引擎...")
    embeddings = HuggingFaceEndpointEmbeddings(
        model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        huggingfacehub_api_token=hf_token
    )

    # 4. 將資料轉成向量並存入「intent_examples」樓層
    print("💾 正在上傳至雲端轉為向量並存入 1 樓 (intent_examples)...")
    Chroma.from_texts(
        texts=texts,
        metadatas=metadatas,
        embedding=embeddings, # 這裡把剛剛宣告的 embeddings 丟進去
        collection_name="intent_examples", # 🌟 這是 1 樓的門牌號碼
        persist_directory=CHROMA_PERSIST_DIR
    )
    
    print("\n🎉 大功告成！邱比特的「意圖警衛室」已建置完畢！")
    print("你可以去修改 API 邏輯了喵！")

if __name__ == "__main__":
    ingest_intents()