import requests
import xmltodict
import urllib3
import re
import time
from datetime import datetime, timedelta
from decimal import Decimal
from ..models import CpiData, TaskRunLog
from ..database import SessionLocal
import logging

logger = logging.getLogger("app_logger")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CPI_URL = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230555/pr0101a1m.xml"
TASK_NAME = "cpi"


# ── 工具：寫入一筆執行紀錄 ──────────────────────────────────────
def _write_log(status: str, duration_ms: int = 0,
               rows_added: int = 0, rows_updated: int = 0,
               message: str = ""):
    """獨立 session 寫入，不受主程式 rollback 影響"""
    try:
        with SessionLocal() as log_db:
            log_db.add(TaskRunLog(
                task_name=TASK_NAME,
                status=status,
                duration_ms=duration_ms,
                rows_added=rows_added,
                rows_updated=rows_updated,
                message=message[:200] if message else "",
            ))
            log_db.commit()
    except Exception as log_err:
        logger.error(f"[CPI] 寫入 task_run_log 失敗: {log_err}")


# ── XML 結構搜尋（不動原本邏輯）────────────────────────────────
def find_data_items(obj):
    """強效搜尋：自動在 XML 字典結構中尋找資料列表"""
    if isinstance(obj, list):
        if len(obj) > 0 and isinstance(obj[0], dict) and "Item" in obj[0]:
            return obj
        for item in obj:
            res = find_data_items(item)
            if res:
                return res

    if isinstance(obj, dict):
        targets = ["pr0101a1m", "Row", "pr0101a1", "Data"]
        for target in targets:
            if target in obj:
                val = obj[target]
                return val if isinstance(val, list) else [val]
        for k, v in obj.items():
            if k.startswith("@"):
                continue
            res = find_data_items(v)
            if res:
                return res

    return None


# ── 主程式 ──────────────────────────────────────────────────────
def fetch_and_update_cpi():
    """
    抓取 CPI 指數並存入資料庫，僅保留最近 6 年數據。
    包含智慧跳過機制：若資料庫已有最新月份資料，則不進行爬取。
    每次執行結果都會寫入 task_run_logs 方便監控。
    """
    logger.info("--- [CPI 檢查程序啟動] ---")
    start_time = time.time()

    current_date = datetime.now()
    current_year = current_date.year
    min_save_year = current_year - 5

    with SessionLocal() as db:

        # ── 智慧跳過邏輯 ────────────────────────────────────────
        last_month_date = current_date.replace(day=1) - timedelta(days=1)
        target_period_str = last_month_date.strftime("%YM%m")

        latest_record = (
            db.query(CpiData)
            .order_by(CpiData.period.desc())
            .first()
        )

        if latest_record:
            logger.info(
                f"🔍 資料庫目前最新資料為: {latest_record.period} "
                f"(目標: {target_period_str})"
            )
            if latest_record.period >= target_period_str:
                msg = f"資料已是最新 ({latest_record.period})，跳過爬取"
                logger.info(f"✅ [CPI 爬蟲] {msg}")
                print(f"✅ [CPI 爬蟲] {msg}")

                # ★ 寫入 skip 紀錄
                _write_log(
                    status="skip",
                    duration_ms=int((time.time() - start_time) * 1000),
                    message=msg,
                )
                return

        # ── 正式爬蟲邏輯 ────────────────────────────────────────
        logger.info("🚀 資料庫落後或無資料，開始執行爬蟲更新...")

        try:
            response = requests.get(CPI_URL, timeout=30, verify=False)
            response.encoding = "utf-8"
            response.raise_for_status()

            data_dict = xmltodict.parse(response.text)
            items = find_data_items(data_dict)

            if not items:
                msg = "無法在 XML 結構中找到資料節點"
                logger.warning(f"❌ {msg}")

                # ★ 寫入 fail 紀錄
                _write_log(
                    status="fail",
                    duration_ms=int((time.time() - start_time) * 1000),
                    message=msg,
                )
                return

            new_count = 0
            update_count = 0
            skip_count = 0

            for item in items:
                category_name = item.get("Item")
                raw_period = item.get("TIME_PERIOD")
                type_val = item.get("TYPE")
                value = item.get("Item_VALUE")

                if not value or value == "-" or not category_name:
                    continue

                year_part = int(raw_period[:4])
                if year_part < min_save_year:
                    skip_count += 1
                    continue

                period_str = re.sub(r"[^0-9M]", "", raw_period)

                existing = (
                    db.query(CpiData)
                    .filter(
                        CpiData.category == category_name,
                        CpiData.period == period_str,
                        CpiData.data_type == type_val,
                    )
                    .first()
                )

                val_decimal = Decimal(value)

                if not existing:
                    db.add(CpiData(
                        category=category_name,
                        period=period_str,
                        data_type=type_val,
                        val=val_decimal,
                    ))
                    new_count += 1
                else:
                    if existing.val != val_decimal:
                        existing.val = val_decimal
                        update_count += 1

                if (new_count + update_count) % 500 == 0:
                    db.flush()

            db.commit()

            duration_ms = int((time.time() - start_time) * 1000)
            success_msg = (
                f"新增: {new_count} 筆, "
                f"更新: {update_count} 筆, "
                f"略過舊資料: {skip_count} 筆"
            )
            logger.info(f"✅ [CPI 任務結束] {success_msg} ({duration_ms}ms)")
            print(f"✅ [CPI 任務結束] {success_msg}")

            # ★ 寫入 ok 紀錄
            _write_log(
                status="ok",
                duration_ms=duration_ms,
                rows_added=new_count,
                rows_updated=update_count,
                message=success_msg,
            )

        except Exception as e:
            db.rollback()
            duration_ms = int((time.time() - start_time) * 1000)
            err_msg = str(e)[:200]
            logger.error(f"❌ CPI 抓取程序崩潰: {err_msg}", exc_info=True)

            # ★ 寫入 fail 紀錄
            _write_log(
                status="fail",
                duration_ms=duration_ms,
                message=err_msg,
            )
            raise e