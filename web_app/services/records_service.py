# web_app/services/records_service.py
from sqlalchemy.orm import Session
from decimal import Decimal
from datetime import datetime, date
import pytz
from ..models import AddRecord, Account, Transaction, Notification, Budget, SavingsGoal,AddItem
from web_app.services.game_service import GameService
from sqlalchemy import func


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
        account = db.query(Account).filter(
            Account.user_id == user_id,
            Account.account_name == data.get("account_name")
        ).first()
        if not account:
            account = db.query(Account).filter(Account.user_id == user_id).first()
        if not account:
            raise ValueError("小主人還沒建帳戶喵")

        new_rec = AddRecord(
            user_id=user_id,
            add_date=RecordsService.get_taiwan_now().date(),
            add_amount=amt,
            add_type=True if data.get("record_type") == "income" else False,
            add_class=data.get("add_class", "其他"),
            add_class_icon=data.get("add_class_icon", "📦"),
            account_id=account.account_id,
            add_member=data.get("add_member", "自己"),
            add_tag=data.get("add_tag", "需要"),
            add_note=data.get("add_note", "語音記帳")
        )
        if new_rec.add_type:
            account.current_balance += amt
        else:
            account.current_balance -= amt
        db.add(new_rec)
        db.commit()
        return True

    @staticmethod
    def create_transfer(db: Session, user_id: int, data: dict):
        amt = Decimal(str(data.get("add_amount", 0)))
        accounts = db.query(Account).filter(Account.user_id == user_id).limit(2).all()
        if len(accounts) < 2:
            raise ValueError("轉帳需要至少兩個帳戶喵")

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

    @staticmethod
    def process_record_logic(db: Session, user_id: int, new_record: AddRecord):
        """
        封裝 POST 新增記帳後的所有連鎖反應：餘額更新、預算檢查、儲蓄目標、遊戲任務
        """
        amt = Decimal(str(new_record.add_amount))
        today = date.today()
        first_day_of_month = today.replace(day=1)

        # 1. 查找帳戶
        account = db.query(Account).filter(
            Account.account_id == new_record.account_id
        ).first()
        if not account:
            return False, "找不到指定帳戶"

        if new_record.add_type is False:  # 支出
            account.current_balance -= amt
            if new_record.add_date >= first_day_of_month:
                RecordsService._check_budget_alerts(db, user_id, new_record, amt)
        else:  # 收入
            account.current_balance += amt
            RecordsService._check_savings_goals(db, user_id, new_record, amt)

        # 2. 觸發遊戲任務
        GameService.update_mission_progress(
            db,
            user_id=user_id,
            category='記帳',
            amount=float(new_record.add_amount),
            tag=new_record.add_tag,
            record_class=new_record.add_class,
            note=new_record.add_note,
            add_type=new_record.add_type
        )

        db.commit()
        db.refresh(new_record)
        return True, "Success"  # ← 原本漏掉這行！

    @staticmethod
    def update_record_logic(db: Session, user_id: int, db_record: AddRecord, update_data: dict):
        """
        封裝 PATCH 修改記帳後的所有連鎖反應
        """
        # 1. 還原舊帳戶餘額
        old_account = db.query(Account).filter(
            Account.account_id == db_record.account_id
        ).first()
        if old_account:
            if db_record.add_type is False:
                old_account.current_balance += db_record.add_amount
            else:
                old_account.current_balance -= db_record.add_amount

        # 2. 更新 ORM 物件欄位
        for key, value in update_data.items():
            setattr(db_record, key, value)
        db_record.add_amount = Decimal(str(db_record.add_amount))

        # 3. 查找新帳戶並套用影響
        new_account = db.query(Account).filter(
            Account.account_id == db_record.account_id
        ).first()
        if not new_account:
            return False, "目標帳戶不存在"

        today = date.today()
        amt = db_record.add_amount

        if db_record.add_type is False:  # 支出
            new_account.current_balance -= amt
            if db_record.add_date >= today.replace(day=1):
                RecordsService._check_budget_alerts(db, user_id, db_record, amt)
        else:  # 收入
            new_account.current_balance += amt
            RecordsService._check_savings_goals(db, user_id, db_record, amt)

        # 4. 觸發遊戲任務（PATCH 對應「除錯大師」）
        GameService.update_mission_progress(
            db,
            user_id=user_id,
            category='記帳',
            increment=1
        )

        db.commit()
        db.refresh(db_record)
        return True, "Success"

    @staticmethod
    def _check_budget_alerts(db: Session, user_id: int, record: AddRecord, amount: Decimal):
        """私有方法：檢查支出是否接近或超過預算"""
        today = date.today()
        first_day_of_month = today.replace(day=1)

        budget = db.query(Budget).filter(
            Budget.user_id == user_id,
            Budget.category == record.add_class
        ).first()
        if not budget:
            return

        if budget.amount == 0:
            # 禁止支出分類，任何支出都發通知
            if amount > 0:
                db.add(Notification(
                    user_id=user_id,
                    reminder_title=f"🚫 超額警報：{record.add_class} 已超出預算",
                    category="budget",
                    description=f"您在「{record.add_class}」並未編列預算，但已有支出 {amount:,.0f} 元。",
                    reminder_date_start=today,
                    reminder_time=datetime.now().time(),
                    is_active=True,
                    is_read=False
                ))
            return

        if budget.amount > 0:
            total_spent = db.query(func.sum(AddRecord.add_amount)).filter(
                AddRecord.user_id == user_id,
                AddRecord.add_class == record.add_class,
                AddRecord.add_type == False,
                AddRecord.add_date >= first_day_of_month
            ).scalar() or Decimal(0)

            total_spent += amount  # 加上本次（尚未 commit）
            usage_percent = (total_spent / budget.amount) * 100

            if usage_percent >= 90:
                existing_note = db.query(Notification).filter(
                    Notification.user_id == user_id,
                    Notification.category == "budget",
                    Notification.reminder_title.like(f"%{record.add_class}%"),
                    func.date(Notification.created_at) == today
                ).first()

                if not existing_note:
                    db.add(Notification(
                        user_id=user_id,
                        reminder_title=f"⚠️ 預算警報：{record.add_class} 已達 {usage_percent:.0f}%",
                        category="budget",
                        description=f"您在「{record.add_class}」的支出已達 {total_spent:,.0f} 元，接近預算上限 {budget.amount:,.0f} 元。",
                        reminder_date_start=today,
                        reminder_time=datetime.now().time(),
                        is_active=True,
                        is_read=False
                    ))

    @staticmethod
    def _check_savings_goals(db: Session, user_id: int, record: AddRecord, amount: Decimal):
        """私有方法：檢查收入是否讓儲蓄目標達成"""
        today = date.today()

        goal = db.query(SavingsGoal).filter(
            SavingsGoal.account_id == record.account_id,
            SavingsGoal.user_id == user_id,
            SavingsGoal.status == "active"
        ).first()

        if not goal:
            return

        goal.current_amount += amount

        if goal.current_amount >= goal.target_amount:
            existing_note = db.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.category == "savings",
                Notification.reminder_title.like(f"%{goal.goal_name}%")
            ).first()

            if not existing_note:
                db.add(Notification(
                    user_id=user_id,
                    reminder_title=f"🎉 恭喜！儲蓄目標「{goal.goal_name}」已達成！",
                    category="savings",
                    description=f"太棒了！您已成功存下 {goal.current_amount:,.0f} 元，完成了「{goal.goal_name}」的目標。繼續保持優良的理財習慣！",
                    reminder_date_start=today,
                    reminder_time=datetime.now().time(),
                    is_active=True,
                    is_read=False
                ))
                goal.status = "completed"
                
                
                
    @staticmethod
    def create_add_record_with_items(db: Session, user_id: int, record: AddRecord, items: list[dict]):
        """
        建立主記帳後，同步寫入 add_items 明細
        """
        for idx, item in enumerate(items):
            new_item = AddItem(
                add_id=record.add_id,
                sort_order=item.get("sort_order", idx),
                item_name=item["item_name"],
                item_amount=Decimal(str(item["item_amount"])),
                item_class=item.get("item_class")
            )
            db.add(new_item)
        # 不在這裡 commit，交給呼叫方統一 commit
                
                