from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from web_app.database import SessionLocal  # 請依據你的路徑調整
from web_app.models.models import Notification
import logging

logger = logging.getLogger("app_logger")

def cleanup_old_notifications():
    """自動清理 30 天以前且已讀的通知"""
    db: Session = SessionLocal()
    try:
        # 計算 30 天前的時間點
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        # 執行刪除：(已讀) 且 (建立時間早於 30 天前)
        deleted_count = db.query(Notification).filter(
            Notification.is_read == True,
            Notification.created_at < thirty_days_ago
        ).delete()
        
        db.commit()
        if deleted_count > 0:
            logging.info(f"🧹 [Cleanup] 自動清理完成：已刪除 {deleted_count} 則過期通知。")
    except Exception as e:
        db.rollback()
        logging.error(f"❌ [Cleanup] 清理失敗: {str(e)}")
    finally:
        db.close()
