from decimal import Decimal
from datetime import date, datetime, time

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
    Time,
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
    # --- 新增這個欄位 ---
    line_user_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, unique=True)
    # ------------------
    #記錄登入失敗次數與鎖定時間
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    lockout_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    feedbacks = relationship("Feedback", back_populates="user")

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
        Integer, ForeignKey("accounts.account_id"), nullable=True, index=True
    )
    to_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.account_id"), nullable=True, index=True
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

    reminder_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("members.user_id"), nullable=False)

    reminder_title: Mapped[str] = mapped_column(String(50), nullable=False)
    # 提醒類型：'manual' (手動), 'budget' (預算警告), 'savings' (目標達成)
    category: Mapped[str] = mapped_column(String(20), server_default="manual")

    reminder_date_start: Mapped[date] = mapped_column(Date, nullable=False)

    # 就算忘記傳時間，資料庫也能自動填入「寫入當下」的時間
    reminder_time: Mapped[time] = mapped_column(
        Time,
        server_default=func.current_time(),
        default=lambda: datetime.now().time()
    )

    # 週期：none, daily, weekly, monthly
    repeat_cycle: Mapped[str] = mapped_column(String(20), server_default="none")

    description: Mapped[Optional[str]] = mapped_column(String(200))

    # 狀態控制
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="1") # 是否啟用提醒
    is_read: Mapped[bool] = mapped_column(Boolean, server_default="0")   # 是否已讀(針對系統通知)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

# 6.預算表格
class Budget(Base):
    __tablename__ = "budgets"

    budget_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("members.user_id"), nullable=False)

    # 預算金額
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # 如果 category 和 tag 都是 Null，則視為「月總預算」
    category: Mapped[Optional[str]] = mapped_column(String(50))
    tag: Mapped[Optional[str]] = mapped_column(String(50))

    category_icon: Mapped[Optional[str]] = mapped_column(String(20)) # 儲存 🍔, 🚗 等
    tag_color: Mapped[Optional[str]] = mapped_column(String(20))     # 儲存 #004B97 等

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
    user = relationship("Member", back_populates="feedbacks")

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
# ==========================================
# 新增的遊戲化與成就系統 (Gamification)
# ==========================================

# 13. 每日打卡紀錄 (Julia 負責)
class Checkin(Base):
    __tablename__ = "checkin"
    __table_args__ = (
        UniqueConstraint("user_id", "checkin_date", name="uk_user_date"),
    )

    checkin_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="打卡紀錄唯一ID"
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.user_id"), nullable=False, comment="關聯用戶ID"
    )
    checkin_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="打卡日期(YYYY-MM-DD)"
    )

    streak_count: Mapped[int] = mapped_column(
        Integer, default=1, comment="目前連續打卡天數"
    )
    total_checkins: Mapped[int] = mapped_column(
        Integer, default=0, comment="該用戶歷來總打卡次數"
    )
    earned_xp: Mapped[int] = mapped_column(
        Integer, default=0, comment="本次打卡獲得的經驗值"
    )

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="最後更新時間"
    )


# 14. 任務與卡牌倉庫 (白/沛青)
class MissCardsLibrary(Base):
    __tablename__ = "misscards_library"

    lib_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="唯一識別碼"
    )

    # 對應 ENUM('MISSION', 'CARD', 'ACHIEVEMENT')
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="類型：MISSION, CARD, ACHIEVEMENT"
    )

    title: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="名稱(如：策略喵-INTJ)"
    )

    # 對應 ENUM('NORMAL', 'RARE', 'EPIC')
    difficulty: Mapped[str] = mapped_column(
        String(20), server_default="NORMAL", comment="稀有度/難度"
    )

    category: Mapped[Optional[str]] = mapped_column(
        String(20), comment="屬性(如：I/E/T/F，或 Analysis/Saving)"
    )

    series_name: Mapped[str] = mapped_column(
        String(50), server_default="普通", comment="系列名稱"
    )

    target_val: Mapped[int] = mapped_column(
        Integer, default=1, comment="解鎖門檻"
    )
    xp_reward: Mapped[int] = mapped_column(
        Integer, default=0, comment="達成後獲得的XP"
    )

    # 自關聯：如果是任務，獎勵的卡片 ID 指向自己這張表的 lib_id
    card_reward_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("misscards_library.lib_id"), nullable=True, comment="任務贈送的卡牌lib_id"
    )

    reward_unlock_feature: Mapped[Optional[str]] = mapped_column(
        String(100), comment="集滿系列後解鎖的功能代碼"
    )

    is_hidden: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否為隱藏項目"
    )

    image_url: Mapped[Optional[str]] = mapped_column(
        String(255), comment="喵喵圖片檔案名稱"
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text, comment="成就/卡牌描述"
    )

    # 建立關聯以便查詢獎勵卡片詳情 (可選)
    # reward_card = relationship("MissCardsLibrary", remote_side=[lib_id])


# 15. 每日隨機任務 (沛青 負責)
class DailyMission(Base):
    __tablename__ = "daily_missions"
    __table_args__ = (
        UniqueConstraint("user_id", "slot_num", "created_at", name="uk_user_slot_date"),
        UniqueConstraint("user_id", "lib_id", "created_at", name="uk_user_lib_date"),
    )

    miss_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.user_id"), nullable=False
    )
    lib_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("misscards_library.lib_id"), nullable=False, comment="關聯 Library"
    )

    # 0:進行中, 1:待領取, 2:已領取
    miss_status: Mapped[int] = mapped_column(
        Integer, default=0, comment="0:進行中, 1:待領取, 2:已領取"
    )

    current_val: Mapped[int] = mapped_column(
        Integer, default=0, comment="今日任務進度"
    )

    slot_num: Mapped[Optional[int]] = mapped_column(
        Integer, comment="任務槽位：1, 2, 3"
    )

    # 使用 server_default=func.current_date() 對應 SQL 的 DEFAULT (CURRENT_DATE)
    created_at: Mapped[date] = mapped_column(
        Date, server_default=func.current_date(), comment="任務產生日期"
    )

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )


# 16. 萬能成就與卡牌表 (組長 負責)
class AchCard(Base):
    __tablename__ = "ach_cards"
    __table_args__ = (
        UniqueConstraint("user_id", "lib_id", name="uk_user_lib"),
    )

    uac_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="用戶持有項ID"
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.user_id"), nullable=False, comment="用戶ID"
    )
    lib_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("misscards_library.lib_id"), nullable=False, comment="關聯 Library"
    )

    is_unlocked: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否已獲得/解鎖"
    )

    unlocked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="正式解鎖的時間"
    )

    current_val: Mapped[int] = mapped_column(
        Integer, default=0, comment="累積型數據(如：累積打卡天數)"
    )

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="進度最後更新時間"
    )

# 17. 儲蓄目標
class SavingsGoal(Base):
    __tablename__ = "savings_goals"

    goal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("members.user_id"), nullable=False)

    account_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("accounts.account_id"), nullable=True)

    goal_name: Mapped[str] = mapped_column(String(50), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.0)

    start_date: Mapped[date] = mapped_column(Date, default=date.today)
    target_date: Mapped[Optional[date]] = mapped_column(Date)

    # 目標狀態 (例如: active, completed, failed)
    status: Mapped[str] = mapped_column(String(20), default="active")
    account: Mapped[Optional["Account"]] = relationship("Account")

# 18. 登入紀錄表 (用於顯示最近登入活動)
class LoginActivity(Base):
    __tablename__ = "login_activities"

    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.user_id", ondelete="CASCADE"), nullable=False
    )
    ip_address: Mapped[str] = mapped_column(String(45))
    device_info: Mapped[str] = mapped_column(String(100), server_default="Unknown")
    browser: Mapped[str] = mapped_column(String(100), server_default="Unknown")
    location: Mapped[str] = mapped_column(String(100), server_default="Unknown")
    login_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_current: Mapped[bool] = mapped_column(Boolean, server_default="0")



# 18. 模型評分資料表 (邱比特大腦評測用)
class IntentReviewLog(Base):
    __tablename__ = "intent_review_log"

    review_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("members.user_id", ondelete="CASCADE"), nullable=False)

    user_message: Mapped[str] = mapped_column(Text, nullable=False)

    # AI 預測區塊
    predicted_intent: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)

    # 人類審核區塊
    corrected_intent: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_reviewed: Mapped[int] = mapped_column(Integer, server_default="0") # 0: 未審, 1: 已審

    llm_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 關聯設定 (可選)
    user = relationship("Member")
