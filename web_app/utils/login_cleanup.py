# web_app/utils/login_cleanup.py
from datetime import datetime, timedelta
from ..database import SessionLocal
from ..models import LoginActivity
import logging

def cleanup_old_login_activities():
    """清理 30 天以前的登入紀錄"""
    db = SessionLocal()
    try:
        # 取得「30天前」的時間點
        limit_date = datetime.now() - timedelta(days=30)

        # 執行刪除並取得受影響的列數
        deleted_count = db.query(LoginActivity).filter(
            LoginActivity.login_at < limit_date
        ).delete()

        db.commit()

        if deleted_count > 0:
            logging.info(f"🧹 自動清理：已刪除 {deleted_count} 筆超過 30 天的登入紀錄。")
        else:
            logging.info("🧹 自動清理：檢查完畢，無超過 30 天的過期紀錄。")

    except Exception as e:
        db.rollback()
        logging.error(f"❌ 自動清理登入紀錄失敗: {str(e)}", exc_info=True)
    finally:
        db.close()
