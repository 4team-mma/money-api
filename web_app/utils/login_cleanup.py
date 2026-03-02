# web_app/utils/login_cleanup.py
from datetime import datetime, timedelta
from ..database import SessionLocal
from ..models import LoginActivity
import logging

def cleanup_old_login_activities():
    """清理 30 天以前的登入紀錄"""
    db = SessionLocal()
    try:
        # 計算 30 天前的時間點
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        # 執行刪除
        deleted_count = db.query(LoginActivity).filter(
            LoginActivity.login_at < thirty_days_ago
        ).delete()
        
        db.commit()
        if deleted_count > 0:
            logging.info(f"🧹 自動清理：已刪除 {deleted_count} 筆過期的登入紀錄。")
    except Exception as e:
        db.rollback()
        logging.error(f"❌ 自動清理登入紀錄失敗: {str(e)}")
    finally:
        db.close()