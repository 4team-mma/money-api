# web_app/database.py
import os
import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from dotenv import load_dotenv

# 💡 確保讀取 .env
load_dotenv()

# ---------------------------------------------------------
# 🌟 核心邏輯：自動偵測環境 (雲端 vs 地端)
# ---------------------------------------------------------
IS_ON_RENDER = os.getenv("RENDER") == "true"

# 準備連線參數 (Connect Args)
# TiDB Cloud 強制要求 SSL，Render 環境有內建憑證路徑
connect_args = {}

if IS_ON_RENDER:
    # 【雲端模式】
    DATABASE_URL = os.getenv("DATABASE_URL")
    DEBUG = False 
    # 🌟 重點：Render 上的 Linux 系統憑證路徑
    connect_args = {
        "ssl": {
            "ca": "/etc/ssl/certs/ca-certificates.crt"
        }
    }
else:
    # 【地端模式】
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASS = os.getenv("DB_PASS", "")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_NAME = os.getenv("DB_NAME", "money")
    SAFE_PASS = urllib.parse.quote_plus(DB_PASS)
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{SAFE_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
    # 地端如果是連本地 MySQL 通常不需要 SSL，保持 connect_args 為空即可

# ---------------------------------------------------------

if not DATABASE_URL:
    raise ValueError("❌ 錯誤：找不到環境變數 DATABASE_URL！")

# 建立 SQLAlchemy 引擎
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,  # 🌟 注入 SSL 設定
    pool_size=10,
    max_overflow=6,
    pool_pre_ping=True,  
    pool_recycle=300,    # 💡 專業建議：TiDB 建議縮短回收時間 (例如 300s)，避免閒置連線被砍
    echo=False #DEBUG
)

# 建立 Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

# 資料庫依賴注入
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()