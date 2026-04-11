# ingest_codebase.py
# 擔任 B1 機房的「圖書館管理員」，負責把你的 .py, .vue, .js 分門別類切好並向量化。

import os
import chromadb
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

# 🌟 核心修改：直接引入你寫好的雙引擎兵器庫！
from web_app.services.vector_db_tools import VectorDBTools

# --- 設定要讀取的目錄與排除名單 ---
# ⚠️ 注意這裡：請確認 "../money-frontend/src" 是你前端資料夾的正確名稱！
# 如果你的前端資料夾叫做 "vue-project" 或其他名字，請務必改掉！
TARGET_DIRS = [
    "./web_app/routers", 
    "./web_app/models", 
    "./web_app/schemas", 
    "./web_app/services", 
    "C:/MyData/TW_mobile/money/src"  # 🌟 直接填寫絕對路徑！
]
IGNORE_DIRS = ["node_modules", ".git", "__pycache__", "dist", "venv", ".venv"]
ALLOWED_EXTENSIONS = [".py", ".vue", ".js"]

def get_all_code_files():
    """走訪目錄，收集所有程式碼檔案路徑"""
    file_paths = []
    for target in TARGET_DIRS:
        for root, dirs, files in os.walk(target):
            # 排除不需要的資料夾
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            for file in files:
                if any(file.endswith(ext) for ext in ALLOWED_EXTENSIONS):
                    file_paths.append(os.path.join(root, file))
    return file_paths

def main():
    print("🚀 [B1 機房] 正在啟動全專案程式碼向量化工程...")
    
    # 🌟 核心修正：在啟動之前，先徹底摧毀舊的、尺寸不對的箱子
    try:
        client = chromadb.PersistentClient(path="./.chromadb")
        client.delete_collection("codebase_b1")
        print("💥 已徹底摧毀舊的 384 維度 B1 箱子！")
    except Exception:
        pass # 如果箱子本來就不存在，就當作沒事發生
    
    # 重新向 VectorDBTools 索取新的箱子 (這時它會自動以 768 維度重建)
    try:
        vectorstore = VectorDBTools.get_codebase_store()
    except Exception as e:
        print(f"❌ 初始化本地模型失敗：{e}")
        return

    # (原本清空 ids 的這段程式碼可以保留，當作未來的雙重保險)
    existing_docs = vectorstore.get()
    if existing_docs['ids']:
        print("🧹 清除舊有的 B1 程式碼記憶...")
        vectorstore.delete(ids=existing_docs['ids'])

    files = get_all_code_files()
    print(f"📂 共找到 {len(files)} 個程式碼檔案，準備切分...")

    # --- 根據不同語言，使用專屬的切分器 ---
    # all-minilm輕量模型只能256 到 512 個 Tokens
    # 換成Context 長度高達 8192的nomic-embed-text
    python_splitter = RecursiveCharacterTextSplitter.from_language(language=Language.PYTHON, chunk_size=800, chunk_overlap=100)
    js_splitter = RecursiveCharacterTextSplitter.from_language(language=Language.JS, chunk_size=800, chunk_overlap=100)
    
    all_chunks = []
    
    for file_path in files:
        try:
            loader = TextLoader(file_path, encoding='utf-8')
            doc = loader.load()
            
            # 在每個碎片的 Metadata 標記來源檔案，這是 RAG 找答案的關鍵！
            for d in doc:
                d.metadata["source"] = file_path 
            
            if file_path.endswith(".py"):
                chunks = python_splitter.split_documents(doc)
            elif file_path.endswith(".js") or file_path.endswith(".vue"):
                # Vue 檔案結構類似 JS，這裡用 JS 分詞器處理
                chunks = js_splitter.split_documents(doc)
            else:
                continue
                
            all_chunks.extend(chunks)
        except Exception as e:
            print(f"⚠️ 無法讀取檔案 {file_path}: {e}")

    if not all_chunks:
        print("❌ 沒有切分出任何程式碼片段，請檢查 TARGET_DIRS 路徑是否正確！")
        return

    print(f"✂️ 程式碼切分完畢，共產出 {len(all_chunks)} 個片段。準備存入向量資料庫...")
    
    # --- 存入 ChromaDB ---
    batch_size = 100
    for i in range(0, len(all_chunks), batch_size):
        vectorstore.add_documents(all_chunks[i:i+batch_size])
        print(f"💾 正在寫入第 {i+1} ~ {min(i+batch_size, len(all_chunks))} 筆...")

    print("🎉 [B1 機房] 建置完成！AI 現在可以看懂你的整個專案架構了！")

if __name__ == "__main__":
    main()