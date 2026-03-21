# ingest_knowledge.py
import os
import glob
import shutil
from dotenv import load_dotenv
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEndpointEmbeddings

load_dotenv()

# 🌟 1. 改成指向「資料夾」而不是單一檔案
DATA_DIR = "./web_app/data/"
CHROMA_PERSIST_DIR = "./.chromadb"

def ingest_data():
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        print("❌ 請先在 .env 檔案中設定 HF_TOKEN")
        return

    # 🧹 2. 清除舊的向量資料庫 (避免重複寫入造成 AI 記憶錯亂與資料庫肥大)
    if os.path.exists(CHROMA_PERSIST_DIR):
        print("🧹 清除舊的記憶資料庫...")
        shutil.rmtree(CHROMA_PERSIST_DIR)

    # 📄 3. 自動掃描並讀取資料夾內所有的 .md 檔案
    all_documents = []
    md_files = glob.glob(os.path.join(DATA_DIR, "*.md"))
    
    if not md_files:
        print(f"❌ 在 {DATA_DIR} 找不到任何 .md 檔案！")
        return

    for filepath in md_files:
        print(f"📄 讀取手冊: {filepath}")
        loader = TextLoader(filepath, encoding="utf-8")
        all_documents.extend(loader.load())
    
    # ✂️ 4. 切割段落
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = text_splitter.split_documents(all_documents)
    print(f"✂️ 所有手冊已切割成 {len(chunks)} 個小段落")

    # 🌟 使用 HuggingFace 進行向量化
    embeddings = HuggingFaceEndpointEmbeddings(
        model="sentence-transformers/all-MiniLM-L6-v2",
        huggingfacehub_api_token=hf_token
    )
    
    print("💾 正在上傳至雲端轉為向量並存入本機 ChromaDB...")
    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name="system_manual",
        persist_directory=CHROMA_PERSIST_DIR
    )
    print("✅ 匯入完成！AI 喵喵現在已經學會所有手冊裡的知識了喵！")

if __name__ == "__main__":
    ingest_data()