# web_app/services/vector_db_tools.py
import os
from typing import Optional
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEndpointEmbeddings

load_dotenv()

CHROMA_PERSIST_DIR = "./.chromadb"

class VectorDBTools:
    # 🌟 建立類別變數來「快取」實例，避免重複連線跟讀取硬碟！
    _embeddings = None
    _intent_store = None
    _manual_store = None

    @classmethod
    def _get_embeddings(cls):
        """共用的向量化引擎 (單例模式 Singleton)"""
        if cls._embeddings is None:
            hf_token = os.getenv("HF_TOKEN")
            if not hf_token:
                raise ValueError("找不到 HF_TOKEN，請確認 .env 檔案設定喵！")
                
            print("🚀 [系統] 首次初始化 HuggingFace 向量引擎...")
            cls._embeddings = HuggingFaceEndpointEmbeddings(
                model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                huggingfacehub_api_token=hf_token
            )
        return cls._embeddings

    @classmethod
    def get_manual_store(cls):
        """取得 2 樓：知識圖書館 (單例模式)"""
        if cls._manual_store is None:
            print("📚 [系統] 首次載入知識圖書館 (system_manual)...")
            cls._manual_store = Chroma(
                collection_name="system_manual",
                embedding_function=cls._get_embeddings(),
                persist_directory=CHROMA_PERSIST_DIR
            )
        return cls._manual_store

    @classmethod
    def get_intent_store(cls):
        """取得 1 樓：意圖警衛室 (單例模式)"""
        if cls._intent_store is None:
            print("👮‍♂️ [系統] 首次載入意圖警衛室 (intent_examples)...")
            cls._intent_store = Chroma(
                collection_name="intent_examples",
                embedding_function=cls._get_embeddings(),
                persist_directory=CHROMA_PERSIST_DIR
            )
        return cls._intent_store

    @staticmethod
    def search_manual(query: str, k: int = 5) -> str:
        """在 2 樓搜尋手冊知識"""
        try:
            vectorstore = VectorDBTools.get_manual_store()
            docs = vectorstore.similarity_search(query, k=k)
            
            if not docs:
                return "喵喵在手冊裡找不到相關的說明喵..."
                
            context_text = "\n\n".join([f"【參考段落 {i+1}】\n{doc.page_content}" for i, doc in enumerate(docs)])
            return context_text
            
        except Exception as e:
            print(f"ChromaDB 查詢錯誤: {e}")
            return "喵喵的手冊資料庫連線中斷，請稍後再試喵！"
    
    @staticmethod
    def search_intent(query: str) -> Optional[str]:
        """在 1 樓搜尋意圖防呆範例"""
        try:
            vectorstore = VectorDBTools.get_intent_store()
            
            # 尋找最相似的 1 句話
            docs_and_scores = vectorstore.similarity_search_with_score(query, k=1)
            
            if docs_and_scores:
                doc, score = docs_and_scores[0]
                # 🌟 門檻值：如果你覺得它亂攔截，調低(例如 0.2)；攔截不到，調高(例如 0.4)
                if score < 0.3: 
                    return doc.metadata["intent"] 
            
            return None 
            
        except Exception as e:
            print(f"ChromaDB 意圖查詢錯誤: {e}")
            return None