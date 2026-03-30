# web_app/services/vector_db_tools.py
import os
from dotenv import load_dotenv
from langchain_chroma import Chroma
from typing import Optional

# 🌟 換成最新、最穩定的專屬套件
from langchain_huggingface import HuggingFaceEndpointEmbeddings

load_dotenv()

CHROMA_PERSIST_DIR = "./.chromadb"

class VectorDBTools:
    
    @staticmethod
    def _get_embeddings():
        """共用的向量化引擎 (1樓跟2樓都要用這個來把文字變數字)"""
        hf_token = os.getenv("HF_TOKEN")
        if not hf_token:
            raise ValueError("找不到 HF_TOKEN，請確認 .env 檔案設定喵！")
            
        return HuggingFaceEndpointEmbeddings(
            model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            huggingfacehub_api_token=hf_token
        )

    @staticmethod
    def get_vectorstore():
        """取得 2 樓：知識圖書館 (system_manual)"""
        embeddings = VectorDBTools._get_embeddings() # 呼叫共用引擎
        
        return Chroma(
            collection_name="system_manual",
            embedding_function=embeddings,
            persist_directory=CHROMA_PERSIST_DIR
        )

    @staticmethod
    def search_manual(query: str, k: int = 5) -> str:
        """在 2 樓搜尋手冊知識"""
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
    
    @staticmethod
    def search_intent(query: str) -> Optional[str]: 
        
        """在 1 樓搜尋意圖防呆範例"""
        try:
            embeddings = VectorDBTools._get_embeddings()
            
            vectorstore = Chroma(
                collection_name="intent_examples",
                embedding_function=embeddings,
                persist_directory=CHROMA_PERSIST_DIR
            )
            
            docs_and_scores = vectorstore.similarity_search_with_score(query, k=1)
            
            if docs_and_scores:
                doc, score = docs_and_scores[0]
                if score < 0.3: 
                    return doc.metadata["intent"] 
            
            return None 
            
        except Exception as e:
            print(f"ChromaDB 意圖查詢錯誤: {e}")
            return None