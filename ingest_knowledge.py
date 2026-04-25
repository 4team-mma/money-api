# ingest_knowledge.py
import os
import glob
from dotenv import load_dotenv
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
import chromadb

load_dotenv()

# 🌟 設定路徑
DATA_DIR = "./web_app/data/manuals/"
CHROMA_PERSIST_DIR = "./.chromadb"
IS_CLOUD = os.getenv("IS_CLOUD", "false").lower() == "true"


def get_embeddings():
    """雲端用 Google API，地端用 FastEmbed"""
    if IS_CLOUD:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        print("🌐 [VectorDB] 雲端模式：使用 Google text-embedding-004")
        return GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
    else:
        print("💻 [VectorDB] 地端模式：使用 FastEmbed bge-small-zh-v1.5")
        return FastEmbedEmbeddings(
            model_name="BAAI/bge-small-zh-v1.5",
            cache_dir="./web_app/models/fastembed_cache"
        )


def ingest_data():
    """將手冊資料轉換為向量並存入 ChromaDB"""

    # 🧹 1. 清除舊的「系統手冊」房間
    if os.path.exists(CHROMA_PERSIST_DIR):
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        try:
            client.delete_collection("system_manual")
            print("✅ [清理] 已清除舊的 system_manual 向量庫。")
        except (Exception, ValueError):
            print("✨ [清理] 未偵測到舊房間，將直接建立新的。")

    # 📄 2. 掃描讀取所有 .md 檔案
    all_documents = []
    md_files = glob.glob(os.path.join(DATA_DIR, "*.md"))

    if not md_files:
        print(f"❌ 錯誤：在 {DATA_DIR} 找不到任何 .md 檔案！")
        return

    for filepath in md_files:
        print(f"📄 [載入] 讀取手冊中: {filepath}")
        try:
            loader = TextLoader(filepath, encoding="utf-8")
            all_documents.extend(loader.load())
        except Exception as e:
            print(f"⚠️ [警告] 讀取檔案 {filepath} 失敗: {e}")

    # ✂️ 3. 切割段落
    # 使用 RecursiveCharacterTextSplitter 確保切割邏輯較為智能
    # 500/50適合較長的上下文,400/80適合較密集的重疊
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=80)
    chunks = text_splitter.split_documents(all_documents)
    print(f"✂️ [切割] 手冊已切割為 {len(chunks)} 個段落。")

    # 🚀 4. 初始化 Embedding 引擎
    embeddings = get_embeddings()

    # 💾 5. 存入 ChromaDB
    print("💾 [儲存] 正在將向量存入 ChromaDB...")
    try:
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            collection_name="system_manual",
            client=client,
            collection_metadata={"hnsw:space": "cosine"}
        )
        print("✅ [完成] 匯入成功！AI 喵喵現在已經學會所有手冊裡的知識了喵！")
    except Exception as e:
        print(f"❌ [錯誤] 存入 ChromaDB 失敗: {e}")


if __name__ == "__main__":
    ingest_data()
