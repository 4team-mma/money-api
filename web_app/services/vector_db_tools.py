# web_app/services/vector_db_tools.py
import os
import chromadb
from typing import Optional
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
load_dotenv()

CHROMA_PERSIST_DIR = "./.chromadb"
IS_CLOUD = os.getenv("IS_CLOUD", "false").lower() == "true"


class BaseVectorStore:

    @staticmethod
    def create(client, name, embedding):
        return Chroma(
            client=client,
            collection_name=name,
            embedding_function=embedding,
            collection_metadata={"hnsw:space": "cosine"}
        )


class VectorDBTools:
    _client = None  # 🌟 ChromaDB 原生客戶端 (地基
    _embeddings = None # 💻 地端嵌入引擎 (使用 FastEmbed)
    _intent_store = None # 1F 意圖 Store
    _manual_store = None # 2F 手冊 Store
    _codebase_store = None # B1 機房 Store
    _local_embeddings = None # Ollama 引擎 (供 B1 使用)
    _reranker = None

    @classmethod
    def _get_client(cls):
        """🌟 取得或建立原生 ChromaDB 持久化客戶端 (解決 Chroma 紅線關鍵)"""
        if cls._client is None:
            os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
            cls._client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        return cls._client

    @classmethod
    def clear_caches(cls):
        """🌟 徹底清空連線快取"""
        cls._intent_store = None
        cls._manual_store = None
        cls._codebase_store = None
        cls._client = None
        cls._embeddings = None
        cls._reranker = None
        print("🔄 [VectorDB] cache cleared")

    @classmethod
    def _get_embeddings(cls):
        """💻 強制地端模式：不論在何處，只讀取本地模型檔案"""
        if cls._embeddings is None:
            cls._embeddings = FastEmbedEmbeddings(
                model_name="BAAI/bge-small-zh-v1.5",
                cache_dir="./web_app/models/fastembed_cache"
            )
            print("✅ FastEmbed loaded")
        return cls._embeddings

    @classmethod
    def _get_local_embeddings(cls):
        """💻 Ollama 地端引擎 (供 B1 機房使用)"""
        if cls._local_embeddings is None:
            print("🛡️ loading Ollama nomic-embed-text...")
            from langchain_ollama import OllamaEmbeddings
            cls._local_embeddings = OllamaEmbeddings(model="nomic-embed-text")
        return cls._local_embeddings

    @classmethod
    def _get_reranker(cls):
        return None  # 暫時停用，架構保留等以後有空訓練onnx模型再接

    @classmethod
    def get_manual_store(cls):
        """取得 2 樓：知識圖書館"""
        if cls._manual_store is None:
            print("📚 loading system_manual...")
            cls._manual_store = BaseVectorStore.create(
                cls._get_client(),
                "system_manual",
                cls._get_embeddings()
            )
        return cls._manual_store

    @classmethod
    def get_intent_store(cls):
        """取得 1 樓：意圖警衛室"""
        if cls._intent_store is None:
            print("👮‍♂️ loading 1F intent_examples...")
            cls._intent_store = BaseVectorStore.create(
                cls._get_client(),
                "intent_examples",
                cls._get_embeddings()
            )
        return cls._intent_store

    @classmethod
    def get_codebase_store(cls):
        """🌟 取得 B1：全專案機房 (使用 Ollama)"""
        if cls._codebase_store is None:
            cls._codebase_store = BaseVectorStore.create(
                cls._get_client(),
                "codebase_b1",
                cls._get_local_embeddings()
            )
        return cls._codebase_store

    @staticmethod
    def search_manual(query: str, k: int = 3) -> str:
        """在地端搜尋手冊知識 (移除會報 401 的 Cohere Rerank)"""
        try:
            vectorstore = VectorDBTools.get_manual_store()

            # 1️⃣ 粗撈
            docs = vectorstore.similarity_search(query, k=10)

            if not docs:
                return "喵喵在手冊裡找不到相關的說明喵..."

            # 2️⃣ rerank（如果可用）
            reranker = VectorDBTools._get_reranker()

            if reranker:
                documents = [doc.page_content for doc in docs]
                
                # FastEmbed TextCrossEncoder 的呼叫方式
                scores = list(reranker.rerank(query, documents))
                
                docs = [
                    doc for doc, _ in sorted(
                        zip(docs, scores),
                        key=lambda x: x[1],
                        reverse=True
                    )
                ]

            best_docs = docs[:k]

            context_text = "\n\n".join([
                f"【參考段落 {i+1}】\n{doc.page_content}"
                for i, doc in enumerate(best_docs)
            ])

            return context_text

        except Exception as e:
            print(f"search error: {e}")
            return "資料庫查詢失敗喵！"

    @staticmethod
    def search_intent(query: str) -> Optional[str]:
        """在 1 樓搜尋意圖防呆範例"""
        try:
            # 尋找最相似的 1 句話
            vectorstore = VectorDBTools.get_intent_store()
            docs_and_scores = vectorstore.similarity_search_with_score(query, k=1)

            if docs_and_scores:
                doc, score = docs_and_scores[0]
                # FastEmbed 的餘弦距離分數通常在 0.3~0.5 之間代表很像
                # 改成收緊
                if score < 0.25:
                    return doc.metadata["intent"]

            return None

        except Exception as e:
            print(f"ChromaDB 意圖查詢錯誤: {e}")
            return None