# web_app/services/records_service.py
from sqlalchemy.orm import Session
from decimal import Decimal
from datetime import datetime
import pytz
from ..models import AddRecord, Account, Transaction

class RecordsService:
    @staticmethod
    def get_taiwan_now():
        return datetime.now(pytz.timezone('Asia/Taipei'))

    @staticmethod
    def get_class_icon(class_name: str) -> str:
        icon_map = {
            '飲食': '🍔', '交通': '🚗', '居家': '🏠', '娛樂': '🎮',
            '醫療': '💊', '學習': '📚', '帳單': '🧾', '其他': '📦'
        }
        return icon_map.get(class_name, '📌')

    @staticmethod
    def create_add_record(db: Session, user_id: int, data: dict):
        amt = Decimal(str(data.get("add_amount", 0)))
        # 找對應帳戶
        account = db.query(Account).filter(Account.user_id == user_id, Account.account_name == data.get("account_name")).first()
        if not account:
            account = db.query(Account).filter(Account.user_id == user_id).first()
        if not account: raise ValueError("小主人還沒建帳戶喵")

        new_rec = AddRecord(
            user_id=user_id,
            add_date=RecordsService.get_taiwan_now().date(),
            add_amount=amt,
            add_type=True if data.get("record_type") == "income" else False,
            add_class=data.get("add_class", "其他"),
            add_class_icon=RecordsService.get_class_icon(data.get("add_class", "其他")),
            account_id=account.account_id,
            add_member=data.get("add_member", "自己"),
            add_tag=data.get("add_tag", "需要"),
            add_note=data.get("add_note", "語音記帳")
        )
        # 更新餘額
        if new_rec.add_type: account.current_balance += amt
        else: account.current_balance -= amt
        db.add(new_rec)
        db.commit()
        return True

    @staticmethod
    def create_transfer(db: Session, user_id: int, data: dict):
        amt = Decimal(str(data.get("add_amount", 0)))
        accounts = db.query(Account).filter(Account.user_id == user_id).limit(2).all()
        if len(accounts) < 2: raise ValueError("轉帳需要至少兩個帳戶喵")

        from_acc, to_acc = accounts[0], accounts[1]
        from_acc.current_balance -= amt
        to_acc.current_balance += amt

        new_tx = Transaction(
            user_id=user_id,
            transaction_date=RecordsService.get_taiwan_now().date(),
            from_account_id=from_acc.account_id,
            to_account_id=to_acc.account_id,
            amount=amt,
            transaction_note=data.get("add_note", "語音轉帳")
        )
        db.add(new_tx)
        db.commit()
        return True
