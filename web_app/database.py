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
# Render 雲端環境會自動帶入 RENDER=true 這個環境變數
IS_ON_RENDER = os.getenv("RENDER") == "true"

if IS_ON_RENDER:
    # 【雲端模式】
    # 直接讀取 Render 後台設定的 DATABASE_URL
    DATABASE_URL = os.getenv("DATABASE_URL")
    # 專業建議：雲端正式上線強制關閉 DEBUG，保護系統安全與效能
    DEBUG = False  
else:
    # 【地端模式】
    # 讀取 .env 裡的 DB_ 設定，自動拼湊成本地 MySQL 的 URL
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASS = os.getenv("DB_PASS", "")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_NAME = os.getenv("DB_NAME", "money")
    SAFE_PASS = urllib.parse.quote_plus(DB_PASS)
    # 改用 SAFE_PASS
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{SAFE_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    # 地端依照 .env 設定決定是否開啟 DEBUG
    DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
# ---------------------------------------------------------

if not DATABASE_URL:
    raise ValueError(
        "❌ 錯誤：找不到環境變數 DATABASE_URL！請檢查環境設定。"
    )

# 建立 SQLAlchemy 引擎
engine = create_engine(
    DATABASE_URL,
    pool_size=10,  # 連線池大小
    max_overflow=6,  # 超過 pool_size 時最多再建立幾個連線
    pool_pre_ping=True,  # 每次使用前檢查連線是否有效
    pool_recycle=3600,  # 連線超過 1 小時自動回收
    echo=DEBUG  # 💡 根據環境自動決定是否印出 SQL 指令！
)

# 建立 Session
# autocommit不要自動提交,autoflush不要自動刷新,bind=engine綁定引擎
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 建立 Base 類別（SQLAlchemy 2.0+ 推薦方式）
class Base(DeclarativeBase):
    """ORM 模型的基礎類別，之後所有的 Table Model 都會繼承它"""
    pass

# 資料庫依賴注入
def get_db():
    db = SessionLocal()
    try:
        # 程式會暫停在這裡，等到你的 API 函數執行完畢
        yield db
    except Exception:
        db.rollback()  # 如果 API 發生任何錯誤，這裡會自動回滾
        raise
    finally:
        # 確保伺服器不會因為同時開了太多窗戶而崩潰
        db.close()