# web_app/services/vector_db_tools.py
import os
from dotenv import load_dotenv
from langchain_chroma import Chroma

# 🌟 換成最新、最穩定的專屬套件
from langchain_huggingface import HuggingFaceEndpointEmbeddings

load_dotenv()

CHROMA_PERSIST_DIR = "./.chromadb"

class VectorDBTools:
    @staticmethod
    def get_vectorstore():
        """取得 ChromaDB 連線實例 (使用免費雲端 Embedding)"""
        hf_token = os.getenv("HF_TOKEN")
        if not hf_token:
            raise ValueError("找不到 HF_TOKEN，請確認 .env 檔案設定喵！")
            
        # 🌟 使用新版寫法
        embeddings = HuggingFaceEndpointEmbeddings(
            model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            huggingfacehub_api_token=hf_token
        )
        
        return Chroma(
            collection_name="system_manual",
            embedding_function=embeddings,
            persist_directory=CHROMA_PERSIST_DIR
        )

    @staticmethod
    def search_manual(query: str, k: int = 5) -> str:
        try:
            vectorstore = VectorDBTools.get_vectorstore()
            docs = vectorstore.similarity_search(query, k=k)
            
            if not docs:
                return "喵喵在手冊裡找不到相關的說明喵..."
                
            context_text = "\n\n".join([f"【參考段落 {i+1}】\n{doc.page_content}" for i, doc in enumerate(docs)])
            return context_text
            
        except Exception as e:
            print(f"ChromaDB 查詢錯誤: {e}")
            return "喵喵的手冊資料庫連線中斷，請稍後再試喵！"