# 這是 web_app/models/__init__.py
# 作用：將 models.py 裡面的類別導出到資料夾層級
# web_app/models/__init__.py
from .models import (
    Member,
    Account,
    AddRecord,
    Transaction,
    Notification,
    PasswordReset,
    Feedback,
    CpiData,
    SalaryBenchmark,
    Setting,
    AIConfig,
    Checkin,
    MissCardsLibrary,
    DailyMission,
    AchCard,
    SavingsGoal,
    LoginActivity,
    Budget,
    IntentReviewLog

)

# 這樣別人在寫 from ..models import Member 時，Python 才知道要去哪裡找
