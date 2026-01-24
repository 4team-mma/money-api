import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from dotenv import load_dotenv

# 💡 確保讀取 .env
load_dotenv()

# MySQL 資料庫 URL 設定（優先讀取 .env，否則使用預設值）
DATABASE_URL = os.getenv("DATABASE_URL")

# 判斷是否為開發環境
DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

# 建立 SQLAlchemy 引擎
engine = create_engine(
    DATABASE_URL,
    pool_size=10,        # 連線池大小
    max_overflow=6,      # 超過 pool_size 時最多再建立幾個連線
    pool_pre_ping=True,  # 每次使用前檢查連線是否有效
    pool_recycle=3600,   # 連線超過 1 小時自動回收
    echo=DEBUG,          # 💡 DEBUG 模式下，終端機會直接印出生成的 SQL 指令，對學習很有幫助！
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
        db.rollback() # 如果 API 發生任何錯誤，這裡會自動回滾
        raise
    finally:
        # 確保伺服器不會因為同時開了太多窗戶而崩潰
        db.close()