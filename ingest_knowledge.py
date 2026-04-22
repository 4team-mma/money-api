# ingest_knowledge.py
import os
import glob
from dotenv import load_dotenv
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
# 🌟 導入地端 FastEmbed
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
import chromadb

load_dotenv()

# 🌟 設定路徑
DATA_DIR = "./web_app/data/manuals/"
CHROMA_PERSIST_DIR = "./.chromadb"

def ingest_data():
    """將手冊資料轉換為地端向量並存入 ChromaDB"""
    
    # 🧹 1. 清除舊的「系統手冊」房間 (system_manual)
    # 因為維度從 MiniLM 換成了 bge-small-zh (維度 512)，一定要刪除重寫
    if os.path.exists(CHROMA_PERSIST_DIR):
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        try:
            client.delete_collection("system_manual")
            print("✅ [清理] 已清除舊的 system_manual 向量庫。")
        except (Exception, ValueError):
            print("✨ [清理] 未偵測到舊房間，將直接建立新的。")

    # 📄 2. 自動掃描並讀取資料夾內所有的 .md 檔案
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
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = text_splitter.split_documents(all_documents)
    print(f"✂️ [切割] 手冊已切割為 {len(chunks)} 個段落。")

    # 🚀 4. 使用 FastEmbed 進行地端向量化 (與 VectorDBTools 保持一致)
    print("🚀 [VectorDB] 正在加載 FastEmbed 地端模型 (BAAI/bge-small-zh-v1.5)...")
    embeddings = FastEmbedEmbeddings(
        model_name="BAAI/bge-small-zh-v1.5",
        cache_dir="./web_app/models/fastembed_cache"
    )

    # 💾 5. 存入 ChromaDB
    print("💾 [儲存] 正在將向量存入 ChromaDB...")
    try:
        # 使用 client 模式初始化，確保 Pylance 不會報紅線，且管理更統一
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        
        Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            collection_name="system_manual",
            client=client # 🌟 使用 client 模式，確保一致性
        )
        print("✅ [完成] 匯入成功！AI 喵喵現在已經學會所有手冊裡的知識了喵！")
    except Exception as e:
        print(f"❌ [錯誤] 存入 ChromaDB 失敗: {e}")

if __name__ == "__main__":
    ingest_data()