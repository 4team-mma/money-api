from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Optional
from ..database import Base

# 核心組件 (Core)處理資料庫的「基本型別」與「結構」
from sqlalchemy import (
    Integer,
    String,
    Numeric,
    Date,
    Boolean,
    ForeignKey,
    DateTime,
    TIMESTAMP,
    func,
    Text,
    UniqueConstraint,
)

# 物件關係映射 (ORM)負責將「Python 物件」與「資料表」串接。
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase

# 主要功能是在定義資料庫的結構，
# Mapped[...]：定義這個欄位的 Python 型別。
# mapped_column(...)：定義資料庫層級的設定（如長度、是否允許為空、主鍵等）。
# 如果你的 Base 是在 database.py 定義的，請確保它繼承自 DeclarativeBase
# 如果 database.py 那邊沒改，這邊直接使用原本引入的 Base 即可
# 加入新表格需要再到__init__.py裡面同時新增


# 1. 會員中心 (Julia同學)
class Member(Base):
    __tablename__ = "members"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(300), nullable=False)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    role: Mapped[str] = mapped_column(String(10), server_default="user", index=True)
    status: Mapped[str] = mapped_column(String(10), server_default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    points: Mapped[int] = mapped_column(Integer, default=0)
    job: Mapped[str] = mapped_column(String(100), default="一般民眾")


# 2. 帳戶管理 (育育同學)
class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.user_id"), nullable=False
    )

    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(5), default="NT$")

    initial_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)

    exclude_from_assets: Mapped[bool] = mapped_column(Boolean, default=False)
    account_icon: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )


# 3. 收支紀錄 (白)
class AddRecord(Base):
    __tablename__ = "adds"

    add_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.user_id"), nullable=False
    )

    add_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    add_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    add_type: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # 支出收入True/False

    add_class: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    add_class_icon: Mapped[str] = mapped_column(String(20), nullable=False)

    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.account_id"), nullable=False, index=True
    )

    add_member: Mapped[str] = mapped_column(String(10), nullable=False)

    add_tag: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    add_note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )


# 4. 轉帳紀錄 (白)
class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.user_id"), nullable=False
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # 1. 這是外鍵欄位，指向小寫的資料表 'accounts'
    from_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.account_id"), nullable=False, index=True
    )
    to_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.account_id"), nullable=False, index=True
    )
    transaction_note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # 2. 這是關聯物件，變數名稱絕對不能叫 from_account_id (會跟上面衝突)
    # 第一個參數要指向類別名 "Account" (大寫)
    # 由於有多個外鍵指向同一張表，必須指定 foreign_keys
    from_account = relationship("Account", foreign_keys=[from_account_id])
    to_account = relationship("Account", foreign_keys=[to_account_id])


# 5. 提醒/行事曆 (沛青同學)
class Notification(Base):
    __tablename__ = "notifications"

    reminder_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.user_id"), nullable=False
    )

    reminder_title: Mapped[str] = mapped_column(String(20), nullable=False)
    reminder_date_start: Mapped[date] = mapped_column(Date, nullable=False)
    reminder_date_end: Mapped[Optional[date]] = mapped_column(Date)

    reminder_time: Mapped[timedelta] = mapped_column(String(10), default="10:00:00")
    repeat_cycle: Mapped[Optional[str]] = mapped_column(String(20))
    description: Mapped[Optional[str]] = mapped_column(String(200))
    # 補上時間戳記
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )


# 7. 忘記密碼表格 (白)
class PasswordReset(Base):
    __tablename__ = "password_resets"

    reset_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.user_id", ondelete="CASCADE"), nullable=False
    )

    email: Mapped[str] = mapped_column(String(100), nullable=False)
    otp_code: Mapped[str] = mapped_column(String(6), nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

# 8. 回饋表格 (育育)
class Feedback(Base):
    __tablename__ = "feedbacks"

    feedback_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # 連結到會員中心
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.user_id"), nullable=False
    )

    # 前端填寫的使用者名稱
    feedback_name: Mapped[str] = mapped_column(String(50), nullable=False)
    # 問題類型 (例如：Bug、建議)
    question_type: Mapped[str] = mapped_column(String(10), nullable=False)
    # 使用頁面 (例如 'web')
    use_page: Mapped[str] = mapped_column(String(10), nullable=False)
    # 詳細內容
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # --- 新增/修改的管理者回覆欄位 ---
    # 管理者回覆內容 (可為空)
    admin_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    # 是否已回覆 (0: 未回, 1: 已回)
    is_replied: Mapped[int] = mapped_column(Integer, server_default="0") 
    # 註：SQLAlchemy 中 Boolean 通常對應 TINYINT，也可以寫 Mapped[bool] = mapped_column(Boolean, default=False)
    # 回覆時間
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 建立時間
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 如果有需要，可以建立與 Member 的關聯
    # user = relationship("Member")

# 9. CPI 物價指數資料 (白)
class CpiData(Base):
    __tablename__ = "cpi_data"

    cpi_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 對應 category VARCHAR(100)
    category: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="對應 Item (例如: 食物類)"
    )

    # 對應 period VARCHAR(10)
    period: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="對應 TIME_PERIOD (例如: 2025M10)"
    )

    # 對應 data_type VARCHAR(20)
    data_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="對應 TYPE (原始值 或 年增率)"
    )

    # 對應 val DECIMAL(10, 2)
    val: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, comment="對應 Item_VALUE"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # 設定複合唯一鍵 (Category + Period + DataType 必須唯一)
    __table_args__ = (
        UniqueConstraint("category", "period", "data_type", name="unique_cpi_record"),
    )


# 10. Salary薪資表格 (白)
class SalaryBenchmark(Base):
    __tablename__ = "salary_benchmarks"

    salary_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # 行業別 (例如: 製造業)
    industry: Mapped[str] = mapped_column(String(100), nullable=False)
    # 週期 (例如: 2025M12)
    period: Mapped[str] = mapped_column(String(10), nullable=False)
    # 類型 (例如: 經常性薪資、總薪資)
    salary_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # 是否為實質薪資 (0: 名目, 1: 實質)
    salary_is_real: Mapped[int] = mapped_column(Integer, nullable=False)
    # 薪資金額
    salary_val: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # 建立時間
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # 修改時間
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )
    # 設定複合唯一鍵，確保資料不重複
    __table_args__ = (
        UniqueConstraint(
            "industry",
            "period",
            "salary_type",
            "salary_is_real",
            name="unique_salary_record",
        ),
    )
    
# 11. 系統/個人偏好設定 (User Settings)
class Setting(Base):
    __tablename__ = "settings"

    setting_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.user_id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # 【區塊一：個人檔案 Profile】
    avatar_url: Mapped[Optional[str]] = mapped_column(String(255), comment="頭像路徑")
    birthday: Mapped[Optional[date]] = mapped_column(Date, comment="生日")
    about: Mapped[Optional[str]] = mapped_column(String(500), comment="自我介紹")

    # 【區塊二：系統功能偏好 Logic】
    # 使用 String(20) 來對應 SQL 的 ENUM
    budget_cycle: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="monthly", comment="預算週期: monthly, weekly, yearly"
    )
    budget_alert_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="75", comment="預算提醒水位(%)"
    )
    start_of_week: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", comment="週起始日 0=週日, 1=週一"
    )

    # 【區塊三：介面外觀 Appearance】
    app_theme: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="light", comment="前台網頁主題"
    )
    admin_theme: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="mma_light", comment="後台管理系統主題"
    )

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    # 建立與 Member 的一對一關係 (可選)
    # member = relationship("Member", back_populates="setting")


# 12. AI 模型配置 (AI Configs)
class AIConfig(Base):
    __tablename__ = "ai_configs"

    config_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.user_id", ondelete="CASCADE"), nullable=False
    )

    # 對應 ENUM('gemini', 'ollama')
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    
    api_key: Mapped[Optional[str]] = mapped_column(String(500), comment="加密後的金鑰")
    base_url: Mapped[str] = mapped_column(
        String(255), server_default="http://localhost:11434", comment="Ollama 地端網址"
    )
    model_version: Mapped[str] = mapped_column(String(50), nullable=False, comment="模型名稱")

    system_prompt: Mapped[Optional[str]] = mapped_column(Text, comment="AI 的人格設定")
    max_tokens: Mapped[int] = mapped_column(Integer, server_default="2000")
    
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

#####新增

# 13. 每日打卡紀錄 (Julia 負責)
# class Checkin(Base):
#     __tablename__ = "checkin"

#     checkin_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     user_id: Mapped[int] = mapped_column(
#         Integer, ForeignKey("members.user_id"), nullable=False
#     )

#     checkin_date: Mapped[date] = mapped_column(Date, nullable=False)
    
#     # 當前連續天數
#     streak_count: Mapped[int] = mapped_column(Integer, server_default="1", comment="當前連續天數")
#     # 生涯累計打卡數
#     total_checkins: Mapped[int] = mapped_column(Integer, server_default="1", comment="生涯累計打卡數")

#     updated_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP, server_default=func.now(), onupdate=func.now()
#     )

#     # 建立複合唯一鍵，確保同一用戶在同一日期只能有一筆打卡紀錄
#     __table_args__ = (
#         UniqueConstraint("user_id", "checkin_date", name="uk_user_date"),
#     )


# 14. 每日隨機任務 (沛青 負責)
# class DailyMission(Base):
#     __tablename__ = "daily_missions"

#     miss_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     user_id: Mapped[int] = mapped_column(
#         Integer, ForeignKey("members.user_id"), nullable=False
#     )

#     title: Mapped[str] = mapped_column(String(100), nullable=False)
#     # 任務難度 (EASY, NORMAL, HARD)
#     difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
#     # 屬性分類 (例如: Analysis(T), Feeling(F) 等，用於 MBTI 成就判定)
#     category: Mapped[Optional[str]] = mapped_column(String(20), comment="對應屬性標籤")
    
#     xp_reward: Mapped[int] = mapped_column(Integer, nullable=False)
    
#     # 任務狀態 (0:進行中, 1:待領取, 2:已領取)
#     status: Mapped[int] = mapped_column(Integer, server_default="0", comment="0:進行中, 1:待領取, 2:已領取")

#     created_at: Mapped[date] = mapped_column(Date, nullable=False)
#     updated_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP, server_default=func.now(), onupdate=func.now()
#     )


# 15. 萬能成就與卡牌表 (組長 負責 - 整合圖鑑與進度)
# class AchievementCard(Base):
#     __tablename__ = "ach_cards"

#     ac_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     user_id: Mapped[int] = mapped_column(
#         Integer, ForeignKey("members.user_id"), nullable=False
#     )
    
#     # 成就/卡片編號 (用於對應前端的資產或定義)
#     ach_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="成就/卡片編號")
    
#     mbti_type: Mapped[Optional[str]] = mapped_column(String(10), comment="MBTI 屬性")
#     series_name: Mapped[str] = mapped_column(String(50), server_default="普通")
#     title: Mapped[str] = mapped_column(String(50), nullable=False)
    
#     # 達成門檻與目前進度
#     target_val: Mapped[int] = mapped_column(Integer, nullable=False, comment="達成門檻")
#     current_val: Mapped[int] = mapped_column(Integer, server_default="0", comment="目前進度")
    
#     # 狀態標籤
#     is_unlocked: Mapped[bool] = mapped_column(Boolean, server_default="0")
#     is_hidden: Mapped[bool] = mapped_column(Boolean, server_default="0")
    
#     unlocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
#     updated_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP, server_default=func.now(), onupdate=func.now()
#     )

#     # 確保同一用戶對同一成就 ID 只有一筆進度資料
#     __table_args__ = (
#         UniqueConstraint("user_id", "ach_id", name="uk_user_ach"),
#     )