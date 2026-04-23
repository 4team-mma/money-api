# ingest_intents.py
import os
import pandas as pd
from dotenv import load_dotenv
from langchain_chroma import Chroma
# 🌟 核心改動：改用地端 FastEmbed
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
import chromadb

# 🌟 匯入資料庫連線與模型
from web_app.database import SessionLocal
from web_app.models.models import IntentReviewLog

load_dotenv()

# 檔案路徑設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 你的基礎題庫 (Excel)
TEST_DATA_FILE = os.path.join(BASE_DIR, "web_app", "temp", "excel", "hard_cases.xlsx")
CHROMA_PERSIST_DIR = os.path.join(BASE_DIR, ".chromadb")


def ingest_intents():
    """建立或更新 1F 意圖警衛室 (地端向量版)"""
    
    texts = []
    metadatas = []

    # ==========================================
    # 來源 A: 讀取基礎題庫 (Excel)
    # ==========================================
    if os.path.exists(TEST_DATA_FILE):
        df = pd.read_excel(TEST_DATA_FILE)
        # 過濾掉空值，確保資料乾淨
        df = df.dropna(subset=['text', 'intent'])

        texts.extend(df['text'].astype(str).tolist())
        metadatas.extend([{"intent": str(intent), "source": "excel_base"} for intent in df['intent'].tolist()])
        print(f"✔️ Excel loading {len(df)} file")
    else:
        print(f"⚠️ 找不到基礎題庫 {TEST_DATA_FILE}，跳過 Excel 載入。")

    # ==========================================
    # 🌟 來源 B: 讀取人類導師修正的錯題 (MySQL)
    # ==========================================
    db = SessionLocal()
    try:
        # 撈取已經由人類審核過的正確意圖紀錄
        reviewed_logs = db.query(IntentReviewLog).filter(
            IntentReviewLog.is_reviewed == 1,
            IntentReviewLog.corrected_intent.isnot(None)
        ).all()

        for log in reviewed_logs:
            texts.append(str(log.user_message))
            metadatas.append({"intent": str(log.corrected_intent), "source": "human_review"})

        print(f"✔️  MySQL loading {len(reviewed_logs)} Human Review")
    except Exception as e:
        print(f"❌ 無法連線資料庫或撈取錯誤，將只使用 Excel 資料。錯誤原因: {e}")
    finally:
        db.close()

    # 檢查是否真的有資料要灌入
    if not texts:
        print("❌ 沒有任何資料可以建立警衛室，腳本結束。")
        return

    # ==========================================
    # 準備 ChromaDB 寫入 (1F 警衛室清理)
    # ==========================================
    if os.path.exists(CHROMA_PERSIST_DIR):
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        try:
            # 🔪 只刪除 1F 的房間，不影響其他資料
            client.delete_collection("intent_examples")
            print("✅ clean old intend library database")
        except Exception:
            print("💡 1樓警衛室目前還是空的，我們直接開始動工建立！")

    # 🚀 啟動 FastEmbed 地端向量化引擎 (與全專案保持一致)
    print("🚀 [VectorDB] 正在加載 FastEmbed 地端模型 (BAAI/bge-small-zh-v1.5)...")
    embeddings = FastEmbedEmbeddings(
        model_name="BAAI/bge-small-zh-v1.5",
        cache_dir="./web_app/models/fastembed_cache"
    )

    print("💾 turn vector to 1F intent_examples...")
    try:
        # 使用原生 Client 模式寫入，解決 Pylance 報錯並提升穩定性
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        
        Chroma.from_texts(
            texts=texts,
            metadatas=metadatas,
            embedding=embeddings,
            collection_name="intent_examples",
            client=client, # 🌟 使用 client 模式
            collection_metadata={"hnsw:space": "cosine"}
        )
        print("\n🎉  MySQL 1F Installation is completed")
    except Exception as e:
        print(f"❌ 存入 1F 意圖資料庫失敗: {e}")

if __name__ == "__main__":
    ingest_intents()