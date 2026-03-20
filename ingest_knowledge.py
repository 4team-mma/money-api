# ingest_knowledge.py
# python ingest_knowledge.py
import os
from dotenv import load_dotenv
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

# 🌟 換成最新、最穩定的專屬套件
from langchain_huggingface import HuggingFaceEndpointEmbeddings

load_dotenv()

FILE_PATH = "./web_app/data/manual.md"
CHROMA_PERSIST_DIR = "./.chromadb"

def ingest_data():
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        print("❌ 請先在 .env 檔案中設定 HF_TOKEN")
        return

    print(f"📄 準備讀取手冊: {FILE_PATH}")
    loader = TextLoader(FILE_PATH, encoding="utf-8")
    documents = loader.load()
    
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = text_splitter.split_documents(documents)
    print(f"✂️ 手冊已切割成 {len(chunks)} 個小段落")

    # 🌟 使用新版寫法 (參數名稱也變了)
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
    print("✅ 匯入完成！AI 喵喵現在已經學會手冊裡的知識了喵！")

if __name__ == "__main__":
    ingest_data()