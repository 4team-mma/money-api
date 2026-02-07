import requests
import xmltodict
import urllib3
import re
from datetime import datetime,timedelta
from decimal import Decimal
from ..models import CpiData
from ..database import SessionLocal
from sqlalchemy import desc
import logging

logger = logging.getLogger("app_logger")

# 屏蔽安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 政府 CPI 月資料連結
CPI_URL = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230555/pr0101a1m.xml"


def find_data_items(obj):
    """💡 強效搜尋：自動在 XML 字典結構中尋找資料列表"""
    # 情況 A: 物件是列表
    if isinstance(obj, list):
        # 啟發式判斷：如果列表第一個元素就是目標欄位，直接回傳
        if len(obj) > 0 and isinstance(obj[0], dict) and "Item" in obj[0]:
            return obj

        # 否則遞迴搜尋子項
        for item in obj:
            res = find_data_items(item)
            if res:
                return res

    # 情況 B: 物件是字典
    if isinstance(obj, dict):
        # 1. 優先匹配已知標籤 (優先度排序)
        # 2026 建議：將常用的標籤抽離成常量或配置
        targets = ["pr0101a1m", "Row", "pr0101a1", "Data"]
        for target in targets:
            if target in obj:
                val = obj[target]
                # 確保回傳格式統一為 list，簡化後續 for 迴圈
                return val if isinstance(val, list) else [val]

        # 2. 深度優先搜尋其餘鍵值
        for k, v in obj.items():
            # 跳過屬性標籤 (xmltodict 以 @ 開頭的內容)
            if k.startswith("@"):
                continue

            res = find_data_items(v)
            if res:
                return res

    return None  # 改為返回 None 以便外部判斷 if not items


def fetch_and_update_cpi():
    """
    抓取 CPI 指數並存入資料庫，僅保留最近 6 年數據。
    包含智慧跳過機制：若資料庫已有最新月份資料，則不進行爬取。
    """
    logger.info("--- [CPI 檢查程序啟動] ---")
    
    current_date = datetime.now()
    current_year = current_date.year
    min_save_year = current_year - 5

    with SessionLocal() as db:
        # ---------------------------------------------------------
        # 🧠 智慧判斷邏輯 (Smart Check)
        # ---------------------------------------------------------
        # 1. 計算「理論上應該有的最新資料」是哪個月？
        #    規則：如果是每個月 5 號前，最新資料應該是「上上個月」
        #    規則：如果是每個月 6 號後，最新資料應該是「上個月」
        #    (這裡簡化處理：直接檢查資料庫最新的那筆，是否為「上個月」或「本月」)
        
        # 取得「上個月」的年份與月份 (例如現在 2月，上個月就是 1月)
        last_month_date = current_date.replace(day=1) - timedelta(days=1)
        target_period_str = last_month_date.strftime("%YM%m") # 格式：2026M01

        # 2. 查詢資料庫目前「最新」的一筆資料是什麼時候
        latest_record = (
            db.query(CpiData)
            .order_by(CpiData.period.desc()) # 用月份倒序
            .first()
        )

        if latest_record:
            logger.info(f"🔍 資料庫目前最新資料為: {latest_record.period} (目標: {target_period_str})")
            
            # 如果資料庫已經有「上個月」的資料 (或者因為某些原因已經有本月的)
            # 或者是 5 號以前，資料庫有「上上個月」的其實也算最新，但為了保險，
            # 我們只要判斷：如果 Database 的最新月份 >= 上個月，就代表已經更新過了。
            if latest_record.period >= target_period_str:
                msg = "✅ [CPI 爬蟲] 檢測到資料已是最新，跳過本次爬蟲任務。"
                logger.info("✅ 檢測到資料已是最新，跳過本次爬蟲任務。")
                print(msg)
                return # <--- 直接結束，不再發送 Request 也不跑迴圈
        
        # ---------------------------------------------------------
        # 以下為原本的爬蟲邏輯 (只有當上面檢查沒過時才會執行)
        # ---------------------------------------------------------
        logger.info("🚀 資料庫落後或無資料，開始執行爬蟲更新...")
        
        try:
            response = requests.get(CPI_URL, timeout=30, verify=False)
            response.encoding = "utf-8"
            response.raise_for_status()

            data_dict = xmltodict.parse(response.text)
            items = find_data_items(data_dict)

            if not items:
                logger.warning("❌ 錯誤：無法在 XML 結構中找到資料節點。")
                return

            new_count = 0
            update_count = 0
            skip_count = 0

            # 預先抓出資料庫現有的所有 (Category, Period, Type) 組合，避免迴圈內 N+1 查詢
            # 這能解決你看到的那堆 "SELECT ..." 洗版問題
            # 但因為你的資料量不大，Smart Check 已經能解決 99% 的情況，這邊維持原樣即可。

            for item in items:
                # ... (原本的中間邏輯保持不變) ...
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

                val_float = Decimal(value)

                if not existing:
                    db.add(
                        CpiData(
                            category=category_name,
                            period=period_str,
                            data_type=type_val,
                            val=val_float,
                        )
                    )
                    new_count += 1
                else:
                    if existing.val != val_float:
                        existing.val = val_float
                        update_count += 1

                if (new_count + update_count) % 500 == 0:
                    db.flush()

            db.commit()
            success_msg = f"✅ [CPI 任務結束] 新增: {new_count} 筆, 更新: {update_count} 筆"
            logger.info(
                success_msg
            )
            print(success_msg) # 顯示在終端機

        except Exception as e:
            db.rollback()
            logger.error(f"❌ CPI 抓取程序崩潰: {str(e)}", exc_info=True)
            raise e
