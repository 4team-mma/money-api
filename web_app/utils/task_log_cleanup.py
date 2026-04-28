from ..database import SessionLocal
from ..models import TaskRunLog
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def cleanup_old_task_logs(keep_days: int = 90):
    """清理超過 90 天的任務執行紀錄"""
    cutoff = datetime.now() - timedelta(days=keep_days)
    with SessionLocal() as db:
        deleted = (
            db.query(TaskRunLog)
            .filter(TaskRunLog.ran_at < cutoff)
            .delete()
        )
        db.commit()
    logger.info(f"[TaskLog 清理] 已刪除 {deleted} 筆超過 {keep_days} 天的紀錄")