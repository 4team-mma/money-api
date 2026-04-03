# python ingest_intents.py
import os
import pandas as pd
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEndpointEmbeddings
import chromadb

# 🌟 匯入你的資料庫連線與模型 (請根據你專案的實際路徑調整)
from web_app.database import SessionLocal
from web_app.models.models import IntentReviewLog # 假設這張表對應的 ORM Model 在這裡

load_dotenv()

# 檔案路徑設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 你的基礎題庫
TEST_DATA_FILE = os.path.join(BASE_DIR, "web_app", "temp", "excel", "hard_cases.xlsx")
CHROMA_PERSIST_DIR = os.path.join(BASE_DIR, ".chromadb")


def ingest_intents():
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        print("❌ 請先在 .env 檔案中設定 HF_TOKEN")
        return

    texts = []
    metadatas = []

    # ==========================================
    # 來源 A: 讀取基礎題庫 (Excel)
    # ==========================================
    if os.path.exists(TEST_DATA_FILE):
        print(f"📊 正在讀取基礎防呆題庫: {TEST_DATA_FILE}")
        df = pd.read_excel(TEST_DATA_FILE)
        df = df.dropna(subset=['text', 'intent'])

        texts.extend(df['text'].astype(str).tolist())
        metadatas.extend([{"intent": str(intent), "source": "excel_base"} for intent in df['intent'].tolist()])
        print(f"✔️ 從 Excel 載入 {len(df)} 筆基礎資料。")
    else:
        print(f"⚠️ 找不到基礎題庫 {TEST_DATA_FILE}，跳過 Excel 載入。")

    # ==========================================
    # 🌟 來源 B: 讀取人類導師修正的錯題 (MySQL)
    # ==========================================
    try:
        db = SessionLocal()
        print("🗄️ 正在連線 MySQL 獲取人類導師修正的精華錯題...")
        reviewed_logs = db.query(IntentReviewLog).filter(
            IntentReviewLog.is_reviewed == 1,
            IntentReviewLog.corrected_intent.isnot(None)
        ).all()

        for log in reviewed_logs:
            texts.append(str(log.user_message))
            metadatas.append({"intent": str(log.corrected_intent), "source": "human_review"})

        print(f"✔️ 從 MySQL 載入 {len(reviewed_logs)} 筆人類審核錯題。")
    except Exception as e:
        print(f"❌ 無法連線資料庫或撈取錯誤，將只使用 Excel 資料。錯誤原因: {e}")
    finally:
        db.close()

    # 檢查是否真的有資料要灌入
    if not texts:
        print("❌ 沒有任何資料可以建立警衛室，腳本結束。")
        return

    print(f"\n🔍 總共準備了 {len(texts)} 筆意圖範例準備進行向量化！")

    # ==========================================
    # 準備 ChromaDB 寫入
    # ==========================================
    if os.path.exists(CHROMA_PERSIST_DIR):
        print("🧹 準備清理舊的意圖資料庫...")
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        try:
            client.delete_collection("intent_examples")
            print("✅ 已清空舊的意圖資料庫！")
        except Exception:
            print("💡 1樓警衛室目前還是空的，我們直接開始動工建立！")
            pass

    print("🧠 正在啟動 HuggingFace 向量化引擎...")
    embeddings = HuggingFaceEndpointEmbeddings(
        model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        huggingfacehub_api_token=hf_token
    )

    print("💾 正在上傳至雲端轉為向量並存入 1 樓 (intent_examples)...")
    Chroma.from_texts(
        texts=texts,
        metadatas=metadatas,
        embedding=embeddings,
        collection_name="intent_examples",
        persist_directory=CHROMA_PERSIST_DIR
    )

    print("\n🎉 大功告成！包含最新 MySQL 錯題記憶的「意圖警衛室」已建置完畢！")

if __name__ == "__main__":
    ingest_intents()
