from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from web_app.database import SessionLocal  # 請依據你的路徑調整
from web_app.models.models import Notification
import logging

logger = logging.getLogger("app_logger")

def cleanup_old_notifications():
    """自動清理 30 天以前且已讀的通知"""
    # 使用 context manager 自動管理 session 生命週期
    with SessionLocal() as db:
        try:
            thirty_days_ago = datetime.now() - timedelta(days=30)
            
            deleted_count = db.query(Notification).filter(
                Notification.is_read == True,
                Notification.created_at < thirty_days_ago
            ).delete(synchronize_session=False) # 增加效能，不更新當前 session 快取
            
            db.commit()
            if deleted_count > 0:
                logger.info(f"🧹 [Cleanup] 自動清理完成：已刪除 {deleted_count} 則過期通知。")
        except Exception as e:
            db.rollback()
            logger.error(f"❌ [Cleanup] 清理失敗: {str(e)}", exc_info=True)
