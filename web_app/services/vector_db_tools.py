# web_app/services/vector_db_tools.py
import os
from typing import Optional
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEndpointEmbeddings
import cohere
load_dotenv()

CHROMA_PERSIST_DIR = "./.chromadb"

class VectorDBTools:
    _cloud_embeddings = None # ☁️ 雲端引擎
    _local_embeddings = None # 💻 地端引擎
    _embeddings = None
    _intent_store = None
    _manual_store = None
    _cohere_client = None # 🌟 新增 Cohere 客戶端
    _codebase_store = None   # 🌟 B1 機房專屬 Store

    @classmethod
    def _get_embeddings(cls):
        """☁️ 共用的雲端向量化引擎 (給 1F, 2F 用)"""
        if cls._embeddings is None:
            hf_token = os.getenv("HF_TOKEN")
            if not hf_token:
                raise ValueError("找不到 HF_TOKEN，請確認 .env 檔案設定喵！")

            print("🚀 load HuggingFace Embeddings...")
            cls._embeddings = HuggingFaceEndpointEmbeddings(
                model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                huggingfacehub_api_token=hf_token
            )
        return cls._embeddings


    @classmethod
    def _get_local_embeddings(cls):
        """💻 共用的地端向量化引擎 (給 B1 機房用，保護程式碼隱私)"""
        if cls._local_embeddings is None:
            print("🛡️ loading Ollama nomic-embed-text...")
            # 確保你的電腦已經執行過 ollama pull nomic-embed-text
            # 把 import 寫在函數裡面！ Render 啟動只要沒呼叫函數，就不會報錯！
            from langchain_ollama import OllamaEmbeddings
            cls._local_embeddings = OllamaEmbeddings(model="nomic-embed-text")
        return cls._local_embeddings



    @classmethod
    def get_manual_store(cls):
        """取得 2 樓：知識圖書館 (使用雲端)"""
        if cls._manual_store is None:
            print("📚 loading system_manual...")
            cls._manual_store = Chroma(
                collection_name="system_manual",
                embedding_function=cls._get_embeddings(),
                persist_directory=CHROMA_PERSIST_DIR,
                collection_metadata={"hnsw:space": "cosine"}
            )
        return cls._manual_store

    @classmethod
    def get_intent_store(cls):
        """取得 1 樓：意圖警衛室 (使用雲端)"""
        if cls._intent_store is None:
            print("👮‍♂️  loading 1F intent_examples...")
            cls._intent_store = Chroma(
                collection_name="intent_examples",
                embedding_function=cls._get_embeddings(),
                persist_directory=CHROMA_PERSIST_DIR,
                collection_metadata={"hnsw:space": "cosine"}
            )
        return cls._intent_store


    @classmethod
    def get_codebase_store(cls):
        """🌟 取得 B1：全專案機房 (使用地端，絕對隱私)"""
        if cls._codebase_store is None:
            cls._codebase_store = Chroma(
                collection_name="codebase_b1",
                embedding_function=cls._get_local_embeddings(), # 🔒 使用地端引擎
                persist_directory=CHROMA_PERSIST_DIR,
                collection_metadata={
                "hnsw:space": "cosine", 
                #"hnsw:construction_ef": 200, # 資料量破萬可用
                #"hnsw:M": 32 # 資料破萬再參考,會受顯存影響
                }
                
            )
        return cls._codebase_store


    @staticmethod
    def search_manual(query: str, k: int = 3) -> str:
        """在 2 樓搜尋手冊知識 (使用 Cohere 重排)"""
        try:
            vectorstore = VectorDBTools.get_manual_store()

            # 1. Chroma 粗撈 (抓 10 筆)
            docs = vectorstore.similarity_search(query, k=10)

            if not docs:
                return "喵喵在手冊裡找不到相關的說明喵..."

            cohere_client = VectorDBTools._get_cohere_client()

            if cohere_client:
                # 2. 抽出文字內容準備給 Cohere
                doc_texts = [doc.page_content for doc in docs]

                # 3. 呼叫 Cohere API 進行精密打分與重排
                results = cohere_client.rerank(
                    query=query,
                    documents=doc_texts,
                    top_n=k, # 只取前 k 名
                    model='rerank-multilingual-v3.0' # 指定多語言模型
                )

                # 4. 組裝重排後的結果
                best_docs = [docs[res.index] for res in results.results]
            else:
                # 如果沒有設 API Key，就退回原本的 Chroma 排序
                best_docs = docs[:k]

            context_text = "\n\n".join([f"【參考段落 {i+1}】\n{doc.page_content}" for i, doc in enumerate(best_docs)])
            return context_text

        except Exception as e:
            print(f"查詢錯誤: {e}")
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

    @classmethod
    def _get_cohere_client(cls):
        """共用的 Cohere Client (使用雲端)"""
        if cls._cohere_client is None:
            cohere_key = os.getenv("COHERE_API_KEY")
            if not cohere_key:
                print("⚠️ 找不到 COHERE_API_KEY，將不使用重排功能。")
                return None
            print("⚖️  loading Cohere Rerank ...")
            cls._cohere_client = cohere.Client(cohere_key)
        return cls._cohere_client
