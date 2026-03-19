# web_app/services/advisor_tools.py
from sqlalchemy.orm import Session
# ... 他需要的 import ...

class AdvisorTools:
    @staticmethod
    def calculate_baseline_and_anomalies(db: Session, user_id: int) -> str:
        # 讓他在這裡盡情寫他的演算法、抓出超過 15% 的消費...
        # 最後只要回傳一段乾淨的字串給你即可
        return "【本月異常警告】餐飲支出較上月增加 15%，超出基準線 2,000 元..."