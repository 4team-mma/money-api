# ingest_intents.py
import os
import pandas as pd
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
import chromadb

from web_app.database import SessionLocal
from web_app.models.models import IntentReviewLog

load_dotenv()

# 檔案路徑設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 你的基礎題庫 (Excel)
TEST_DATA_FILE = os.path.join(BASE_DIR, "web_app", "temp", "excel", "hard_cases.xlsx")
CHROMA_PERSIST_DIR = os.path.join(BASE_DIR, ".chromadb")

IS_CLOUD = os.getenv("IS_CLOUD", "false").lower() == "true"


def get_embeddings():
    """雲端用 Google API，地端用 FastEmbed"""
    if IS_CLOUD:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        print("🌐 [VectorDB] 雲端模式：使用 Google gemini-embedding-001")
        return GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    else:
        print("💻 [VectorDB] 地端模式：使用 FastEmbed bge-small-zh-v1.5")
        return FastEmbedEmbeddings(
            model_name="BAAI/bge-small-zh-v1.5",
            cache_dir="./web_app/models/fastembed_cache"
        )


def ingest_intents():
    """建立或更新 1F 意圖警衛室"""

    texts = []
    metadatas = []

    # 來源 A: Excel 基礎題庫
    if os.path.exists(TEST_DATA_FILE):
        df = pd.read_excel(TEST_DATA_FILE)
        df = df.dropna(subset=['text', 'intent'])
        texts.extend(df['text'].astype(str).tolist())
        metadatas.extend([{"intent": str(intent), "source": "excel_base"} for intent in df['intent'].tolist()])
        print(f"✔️ Excel loading {len(df)} file")
    else:
        print(f"⚠️ 找不到基礎題庫 {TEST_DATA_FILE}，跳過 Excel 載入。")

    # 來源 B: MySQL 人類審核修正
    db = SessionLocal()
    try:
        reviewed_logs = db.query(IntentReviewLog).filter(
            IntentReviewLog.is_reviewed == 1,
            IntentReviewLog.corrected_intent.isnot(None)
        ).all()
        for log in reviewed_logs:
            texts.append(str(log.user_message))
            metadatas.append({"intent": str(log.corrected_intent), "source": "human_review"})
        print(f"✔️  MySQL loading {len(reviewed_logs)} Human Review")
    except Exception as e:
        print(f"❌ 無法連線資料庫，將只使用 Excel 資料。錯誤原因: {e}")
    finally:
        db.close()

    if not texts:
        print("❌ 沒有任何資料可以建立警衛室，腳本結束。")
        return

    # 清理舊的 1F
    if os.path.exists(CHROMA_PERSIST_DIR):
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        try:
            client.delete_collection("intent_examples")
            print("✅ clean old intend library database")
        except Exception:
            print("💡 1樓警衛室目前還是空的，我們直接開始動工建立！")

    # 🚀 初始化 Embedding 引擎
    embeddings = get_embeddings()

    print("💾 turn vector to 1F intent_examples...")
    try:
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        Chroma.from_texts(
            texts=texts,
            metadatas=metadatas,
            embedding=embeddings,
            collection_name="intent_examples",
            client=client,
            collection_metadata={"hnsw:space": "cosine"}
        )
        print("\n🎉  MySQL 1F Installation is completed")
    except Exception as e:
        print(f"❌ 存入 1F 意圖資料庫失敗: {e}")


if __name__ == "__main__":
    ingest_intents()
