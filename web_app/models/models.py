from decimal import Decimal
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Integer, String, Numeric, Date, Boolean, 
    ForeignKey, DateTime, TIMESTAMP, func,Text
)
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase
from ..database import Base

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
    
    role: Mapped[str] = mapped_column(String(10), server_default="user")
    status: Mapped[str] = mapped_column(String(10), server_default="active")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    points: Mapped[int] = mapped_column(Integer, default=0)
    job: Mapped[str] = mapped_column(String(100), default='一般用戶')

# 2. 帳戶管理 (育育同學)
class Account(Base):
    __tablename__ = "Accounts"

    account_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("members.user_id"), nullable=False)
    
    account_type: Mapped[str] = mapped_column(String(10), nullable=False)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(5), default="TWD")
    
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)
    
    exclude_from_assets: Mapped[bool] = mapped_column(Boolean, default=False)
    account_icon: Mapped[Optional[str]] = mapped_column(String(5))

# 3. 收支紀錄 (白)
class AddRecord(Base):
    __tablename__ = "Adds"

    add_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("members.user_id"), nullable=False)
    
    add_date: Mapped[date] = mapped_column(Date, nullable=False)
    add_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    add_type: Mapped[bool] = mapped_column(Boolean, nullable=False) # True/False
    
    add_class: Mapped[str] = mapped_column(String(20), nullable=False)
    add_class_icon: Mapped[str] = mapped_column(String(20), nullable=False)
    
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("Accounts.account_id"), nullable=False)
    add_member: Mapped[str] = mapped_column(String(10), nullable=False)
    
    add_tag: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    add_note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

# 4. 轉帳紀錄 (白)
class Transaction(Base):
    __tablename__ = "Transactions"

    transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("members.user_id"), nullable=False)
    
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    from_account: Mapped[str] = mapped_column(String(100), nullable=False)
    to_account: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

# 5. 提醒/行事曆 (沛青同學)
class Notification(Base):
    __tablename__ = "Notifications"

    reminder_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("members.user_id"), nullable=False)
    
    reminder_title: Mapped[str] = mapped_column(String(20), nullable=False)
    reminder_date_start: Mapped[date] = mapped_column(Date, nullable=False)
    reminder_date_end: Mapped[Optional[date]] = mapped_column(Date)
    
    reminder_time: Mapped[str] = mapped_column(String(10), default="10:00:00")
    repeat_cycle: Mapped[Optional[str]] = mapped_column(String(20))
    description: Mapped[Optional[str]] = mapped_column(String(200))

# 7. 忘記密碼表格 (白)
class PasswordReset(Base):
    __tablename__ = "password_resets"

    reset_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("members.user_id", ondelete="CASCADE"), nullable=False)
    
    email: Mapped[str] = mapped_column(String(100), nullable=False)
    otp_code: Mapped[str] = mapped_column(String(6), nullable=False)
    
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    
# 8. 回饋表格 (育育)
class Feedback(Base):
    __tablename__ = "feedbacks"

    feedback_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 連結到會員中心
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("members.user_id"), nullable=False)

    # 前端填寫的使用者名稱
    feedback_name: Mapped[str] = mapped_column(String(50), nullable=False)
    # 問題類型 (例如：Bug、建議)
    question_type: Mapped[str] = mapped_column(String(10), nullable=False)
    # 使用頁面 (後端自動帶入，例如 'web')
    use_page: Mapped[str] = mapped_column(String(10), nullable=False)
    # 詳細內容 (對應 SQL 的 TEXT 型態)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 建立時間
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())