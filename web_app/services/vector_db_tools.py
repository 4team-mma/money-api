# web_app/services/vector_db_tools.py
import os
import chromadb
from typing import Optional
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
import jieba
load_dotenv()

CHROMA_PERSIST_DIR = "./.chromadb"
IS_CLOUD = os.getenv("IS_CLOUD", "false").lower() == "true"


def get_embeddings():
    # 雲端地端都用 FastEmbed，統一、零地區限制
    cache = "/tmp/fastembed_cache" if IS_CLOUD else "./web_app/models/fastembed_cache"
    print(f"{'🌐 雲端' if IS_CLOUD else '💻 地端'} FastEmbed bge-small-zh-v1.5")
    return FastEmbedEmbeddings(
        model_name="BAAI/bge-small-zh-v1.5",
        cache_dir=cache
    )


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
    _sql_cache_store = None # 🌟 1.5F SQL 快取金庫
    _manual_store = None # 2F 手冊 Store
    _codebase_store: Optional[Chroma] = None  # B1 機房 Store
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
        cls._sql_cache_store = None
        cls._manual_store = None
        cls._codebase_store = None
        cls._client = None
        cls._embeddings = None
        cls._reranker = None
        print("🔄 [VectorDB] cache cleared")

    @classmethod
    def _get_embeddings(cls):
        if cls._embeddings is None:
            cls._embeddings = get_embeddings()  # 直接呼叫上面的函式，不重複寫邏輯
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
        """🌟 回傳 'hybrid' 作為輕量級規則排序器的標識"""
        return "hybrid"
    
    @staticmethod
    def _hybrid_rerank(query: str, docs_with_scores):
        """
        🚀 輕量級規則排序：加入 jieba 中文切詞與 Min-Max 分數正規化
        """
        stopwords = {"的", "了", "是", "我", "想", "請問", "怎麼", "如何", "可以", "幫我", "一下"}
        # 1. 🌟 中文切詞 (解決 .split() 對中文無效的問題)
        query_terms = {
            t.strip()
            for t in jieba.lcut(query.lower())
            if len(t.strip()) > 1 and t.strip() not in stopwords
}
        
        # 2. 🌟 提取所有距離，進行 Min-Max 正規化準備
        distances = [dist for _, dist in docs_with_scores]
        min_dist = min(distances) if distances else 0
        max_dist = max(distances) if distances else 0
        if not docs_with_scores:
            return []

        scored_results = []
        for doc, dist in docs_with_scores:
            text = doc.page_content.lower()
            
            # 💡 Embedding 分數轉換：將 Chroma 距離 (越小越好) 轉為 0~1 的分數 (越大越好)
            if max_dist > min_dist:
                emb_score = (max_dist - dist) / (max_dist - min_dist)
            else:
                emb_score = 1.0  # 如果全部距離一樣，就給滿分
            
            # 💡 關鍵字重合度 (過濾掉長度小於2的贅字，如"的"、"了")
            overlap_count = sum(1 for t in query_terms if t in text)
            overlap_score = overlap_count / max(len(query_terms), 1)
            
            # 💡 長度懲罰
            length_penalty = min(len(text) / 1000.0, 1.0)
            
            # 組合最終分數
            final_score = (emb_score * 0.6) + (overlap_score * 0.3) - (length_penalty * 0.1)
            scored_results.append((doc, final_score))

        scored_results.sort(key=lambda x: x[1], reverse=True)
        return scored_results
    
    
    @staticmethod
    def _core_search(query: str, k: int = 3, fetch_k: int = 10):
        """
        🔧 核心檢索引擎：負責把粗撈跟 Rerank 做完，回傳帶分數的文件 List
        這樣其他對外方法就不會寫重複的 Code。
        """
        vectorstore = VectorDBTools.get_manual_store()
        docs_and_scores = vectorstore.similarity_search_with_score(query, k=max(fetch_k, k))

        if not docs_and_scores:
            return []

        reranker = VectorDBTools._get_reranker()
        if reranker == "hybrid":
            sorted_docs_scores = VectorDBTools._hybrid_rerank(query, docs_and_scores)
        else:
            sorted_docs_scores = [(doc, max(0, 1-dist)) for doc, dist in docs_and_scores]

        return sorted_docs_scores[:k]
    
    

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
    def get_sql_cache_store(cls):
        """取得 1.5 樓：SQL 語意快取金庫"""
        if cls._sql_cache_store is None:
            print("🚀 loading 1.5F SQL Cache...")
            cls._sql_cache_store = BaseVectorStore.create(
                cls._get_client(),
                "sql_cache",
                cls._get_embeddings()
            )
        return cls._sql_cache_store



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
        """
        ✅ 給 LLM (FinanceAgentService) 專用的純文字回傳
        完全維持你原本的格式，保證不會與現有 Prompt 衝突。
        """
        try:
            best_docs_scores = VectorDBTools._core_search(query, k)
            if not best_docs_scores:
                return "喵喵在手冊裡找不到相關的說明喵..."

            context_text = "\n\n".join([
                f"【參考段落 {i+1}】\n{doc.page_content}"
                for i, (doc, _) in enumerate(best_docs_scores)
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
        
        
# 快取的 儲存/讀取
    @staticmethod
    def get_cached_sql(query: str) -> Optional[str]:
        """🔍 在 1.5 樓金庫中尋找 SQL 查詢 (已升級為絕對精準比對)"""
        try:
            vectorstore = VectorDBTools.get_sql_cache_store()
            docs_and_scores = vectorstore.similarity_search_with_score(query, k=1)

            if docs_and_scores:
                doc, score = docs_and_scores[0]
                
                # 🌟 終極防護：使用者的問句必須「一模一樣」！
                if doc.page_content.strip() == query.strip():
                    # 💡 把 score 加回 Log 裡面印出來，Pylance 就不會亮黃線了！
                    print(f"🎯 [SQL Cache Hit!] 精準命中快取 (距離分數:{score:.3f}): {doc.page_content}")
                    return doc.metadata["sql_template"]
                else:
                    # 💡 這裡也把 score 印出來，方便你觀察 AI 判斷的數學距離
                    print(f"👀 [SQL Cache Miss] 語意相似(分數:{score:.3f})但字面不同，放棄快取。({doc.page_content} != {query})")

            return None
        except Exception as e:
            print(f"⚠️ SQL 快取查詢錯誤 (初次執行或資料庫為空是正常的): {e}")
            return None

    @staticmethod
    def save_sql_to_cache(query: str, sql_template: str):
        """💾 把 Groq 辛苦寫出來的 SQL 存進金庫"""
        try:
            vectorstore = VectorDBTools.get_sql_cache_store()
            from langchain_core.documents import Document
            
            # 將問題當作向量內容，SQL 語法存進 metadata
            doc = Document(page_content=query, metadata={"sql_template": sql_template})
            vectorstore.add_documents([doc])
            print(f"✅ [SQL Cache Saved] 已將查詢存入快取金庫！")
        except Exception as e:
            print(f"❌ SQL 快取儲存失敗: {e}")


    @staticmethod
    def search_manual_with_sources(query: str, k: int = 3) -> dict:
        """
        ✅ 給 API Endpoint / 前端 UI 用的結構化回傳
        回傳 Python Dict，API 層再 jsonify，前端可以直接 render sources 列表。
        """
        try:
            best_docs_scores = VectorDBTools._core_search(query, k)
            if not best_docs_scores:
                return {"context": "找不到相關的說明喵...", "sources": []}

            sources = []
            context_texts = []
            
            for i, (doc, score) in enumerate(best_docs_scores):
                source_file = doc.metadata.get("source", f"chunk_{i}")
                chunk_text = doc.page_content
                
                context_texts.append(f"【參考來源: {source_file} (關聯度: {score:.2f})】\n{chunk_text}")
                sources.append({
                    "source": source_file,
                    "score": round(score, 3),
                    "chunk": chunk_text[:50] + "..." # 截斷以保護 Payload 大小
                })

            return {
                "context": "\n\n".join(context_texts),
                "sources": sources
            }

        except Exception as e:
            print(f"search error: {e}")
            return {"error": "資料庫查詢失敗喵！", "sources": []}



##################sql快取相關設定:#######################

    @classmethod
    def _get_sql_cache_collection(cls):
        """取得原生 ChromaDB collection（供 list/clear 使用）"""
        return cls._get_client().get_or_create_collection("sql_cache")

    @classmethod
    def delete_cached_sql(cls, user_query: str) -> bool:
        """刪除單筆語意相似的 SQL 快取"""
        try:
            # ✅ 用 LangChain store 搜尋，embedding 才會跟存入時一致
            vectorstore = cls.get_sql_cache_store()
            docs_and_scores = vectorstore.similarity_search_with_score(user_query, k=1)

            if not docs_and_scores:
                return False

            doc, score = docs_and_scores[0]
            print(f"🔍 [快取搜尋] 最近距離: {score:.4f}，內容: {doc.page_content}")

            # 分數門檻放寬到 0.3（LangChain cosine 距離跟原生不同）
            if score < 0.3:
                # 用頁面內容當 ID 去原生 collection 刪除
                raw_collection = cls._get_sql_cache_collection()
                # 找到對應的原生 ID
                results = raw_collection.get(where_document={"$contains": doc.page_content[:50]})
                if results["ids"]:
                    raw_collection.delete(ids=[results["ids"][0]])
                    print(f"🗑️ [SQL 快取] 已刪除：{doc.page_content}")
                    # ✅ 清掉 LangChain store 的記憶體快取，讓下次重新載入
                    cls._sql_cache_store = None
                    return True

            return False
        except Exception as e:
            print(f"❌ 快取刪除失敗: {e}")
            return False

    @classmethod
    def clear_all_sql_cache(cls) -> int:
        """清空全部 SQL 快取，回傳刪除筆數"""
        try:
            collection = cls._get_sql_cache_collection()
            all_items = collection.get()
            count = len(all_items["ids"])
            if count > 0:
                collection.delete(ids=all_items["ids"])
            print(f"🗑️ [SQL 快取] 已清空 {count} 筆")
            return count
        except Exception as e:
            print(f"❌ 快取清空失敗: {e}")
            return 0


