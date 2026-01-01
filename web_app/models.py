from sqlalchemy import Column, Integer, String, Numeric, Date, Boolean, ForeignKey, DateTime, TIMESTAMP, func
from .database import Base


# 1. 會員中心 (Julia同學)
class Member(Base):
    __tablename__ = "members"
    user_id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(100), nullable=False, unique=True)
    password = Column(String(300), nullable=False)
    username = Column(String(50), nullable=False)
    name = Column(String(50), nullable=False)
    role = Column(String(10), server_default="user")
    status = Column(String(10), server_default="active")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime, nullable=True)
    xp = Column(Integer, default=0)
    level = Column(Integer, default=1)
    points = Column(Integer, default=0)
    job = Column(String(100), default='一般用戶')

# 2. 帳戶管理 (育育同學)
class Account(Base):
    __tablename__ = "Accounts"
    account_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("members.user_id"), nullable=False)
    account_type = Column(String(10), nullable=False)
    account_name = Column(String(100), nullable=False)
    currency = Column(String(5), default="TWD")
    initial_balance = Column(Numeric(12, 2), default=0.00)
    current_balance = Column(Numeric(12, 2), default=0.00)
    exclude_from_assets = Column(Boolean, default=False)
    icon_id = Column(String(5))

# 3. 收支紀錄 (白)
class AddRecord(Base):
    __tablename__ = "Adds"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("members.user_id"), nullable=False)
    add_date = Column(Date, nullable=False)
    add_amount = Column(Numeric(12, 2), nullable=False)
    add_type = Column(Boolean, nullable=False)
    add_class = Column(String(20), nullable=False)
    add_class_icon = Column(String(20), nullable=False)
    account_id = Column(Integer, ForeignKey("Accounts.account_id"), nullable=False)
    add_member = Column(String(10), nullable=False)
    add_tag = Column(String(20), nullable=True)
    add_note = Column(String(200), nullable=True)

# 4. 轉帳紀錄 (白)
class Transaction(Base):
    __tablename__ = "Transactions"
    transaction_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("members.user_id"), nullable=False)
    transaction_date = Column(Date, nullable=False)
    from_account = Column(String(100), nullable=False)
    to_account = Column(String(100), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)

# 5. 提醒/行事曆 (沛青同學)
class Notification(Base):
    __tablename__ = "Notifications"
    reminder_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("members.user_id"), nullable=False)
    reminder_title = Column(String(20), nullable=False)
    reminder_date_start = Column(Date, nullable=False)
    reminder_date_end = Column(Date)
    reminder_time = Column(String(10), default="10:00:00")
    repeat_cycle = Column(String(20))
    description = Column(String(200))
    
# 6. 成就收集 (沛青同學)
# class Achievements(Base):
#     __tablename__ = "Achievements"


# 7. 忘記密碼表格 (白)
class PasswordReset(Base):
    __tablename__ = "password_resets"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # 連結到 members 表的 user_id，並設定級聯刪除
    user_id = Column(Integer, ForeignKey("members.user_id", ondelete="CASCADE"), nullable=False)
    # 這裡存入 email 是為了發信方便，不需每次都去 Join member 表
    email = Column(String(100), nullable=False)
    # 驗證碼建議維持 String 格式，防止 0 開頭的數字被截斷
    otp_code = Column(String(6), nullable=False)
    # 過期時間
    expires_at = Column(DateTime, nullable=False)
    # 狀態：0 為未使用 (False)，1 為已使用 (True)
    is_used = Column(Boolean, nullable=False, default=False)
    # 建立時間：使用 server_default=func.now() 讓資料庫自動產生時間
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    
    
# 8. 如果還有表格請往下加~