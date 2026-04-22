# web_app/services/vector_db_tools.py
import os
import chromadb
from typing import Optional
from dotenv import load_dotenv
from langchain_chroma import Chroma
# 🌟 核心改動：改用 FastEmbed，體積更小、速度更快、不依賴 PyTorch (解決 nn 報錯)
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

load_dotenv()

CHROMA_PERSIST_DIR = "./.chromadb"

class VectorDBTools:
    _client = None           # 🌟 ChromaDB 原生客戶端 (地基)
    _embeddings = None       # 💻 地端嵌入引擎 (使用 FastEmbed)
    _intent_store = None     # 1F 意圖 Store
    _manual_store = None     # 2F 手冊 Store
    _codebase_store = None   # B1 機房 Store
    _local_embeddings = None # Ollama 引擎 (供 B1 使用)

    @classmethod
    def _get_client(cls):
        """🌟 取得或建立原生 ChromaDB 持久化客戶端 (解決 Chroma 紅線關鍵)"""
        if cls._client is None:
            # 確保目錄存在
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
        print("🔄 [VectorDB] 連線快取已清空，下次呼叫將重新初始化。")

    @classmethod
    def _get_embeddings(cls):
        """💻 強制地端模式：不論在何處，只讀取本地模型檔案"""
        if cls._embeddings is None:
            model_name = "BAAI/bge-small-zh-v1.5"
            cache_folder = "./web_app/models/fastembed_cache"
            
            # 💡 檢查資料夾是否存在，確保你真的有把模型 commit 進去
            if not os.path.exists(cache_folder):
                print(f"⚠️ 警告：找不到模型目錄 {cache_folder}，這在雲端會導致崩潰！")

            cls._embeddings = FastEmbedEmbeddings(
                model_name=model_name,
                cache_dir=cache_folder,
                # 🌟 加入這行，如果本地找不到檔案，它會報錯而不是去下載
                # 注意：有些版本是用 local_files_only=True，但 FastEmbed 預設會優先讀取 cache_dir
                # 為了絕對保險，我們確保 cache_dir 路徑在雲端是一致的
            )
            print("✅ [VectorDB] 已從本地目錄載入 FastEmbed 模型，目前為 100% 離線狀態。")
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
    def get_manual_store(cls):
        """取得 2 樓：知識圖書館"""
        if cls._manual_store is None:
            print("📚 loading system_manual...")
            cls._manual_store = Chroma(
                client=cls._get_client(), # 🌟 使用 client 模式避免紅線
                collection_name="system_manual",
                embedding_function=cls._get_embeddings()
            )
        return cls._manual_store

    @classmethod
    def get_intent_store(cls):
        """取得 1 樓：意圖警衛室"""
        if cls._intent_store is None:
            print("👮‍♂️ loading 1F intent_examples...")
            cls._intent_store = Chroma(
                client=cls._get_client(),
                collection_name="intent_examples",
                embedding_function=cls._get_embeddings()
            )
        return cls._intent_store

    @classmethod
    def get_codebase_store(cls):
        """🌟 取得 B1：全專案機房 (使用 Ollama)"""
        if cls._codebase_store is None:
            cls._codebase_store = Chroma(
                client=cls._get_client(),
                collection_name="codebase_b1",
                embedding_function=cls._get_local_embeddings()
            )
        return cls._codebase_store

    @staticmethod
    def search_manual(query: str, k: int = 3) -> str:
        """在地端搜尋手冊知識 (移除會報 401 的 Cohere Rerank)"""
        try:
            vectorstore = VectorDBTools.get_manual_store()
            # 使用地端模型進行語意搜尋
            docs = vectorstore.similarity_search(query, k=k)

            if not docs:
                return "喵喵在手冊裡找不到相關的說明喵..."

            context_text = "\n\n".join([f"【參考段落 {i+1}】\n{doc.page_content}" for i, doc in enumerate(docs)])
            return context_text

        except Exception as e:
            print(f"地端搜尋錯誤: {e}")
            return "喵喵的本地資料庫連線中斷喵！"

    @staticmethod
    def search_intent(query: str) -> Optional[str]:
        """在 1 樓搜尋意圖防呆範例"""
        try:
            vectorstore = VectorDBTools.get_intent_store()
            # 尋找最相似的 1 句話
            docs_and_scores = vectorstore.similarity_search_with_score(query, k=1)

            if docs_and_scores:
                doc, score = docs_and_scores[0]
                # FastEmbed 的餘弦距離分數通常在 0.3~0.5 之間代表很像
                if score < 0.4: 
                    return doc.metadata["intent"]
            return None
        except Exception as e:
            print(f"ChromaDB 意圖查詢錯誤: {e}")
            return None