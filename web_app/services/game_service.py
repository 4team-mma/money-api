# web_app/services/game_service.py
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from typing import Optional
from web_app.models import DailyMission, MissCardsLibrary, AddRecord

class GameService:
    @staticmethod
    def update_mission_progress(
        db: Session, 
        user_id: int, 
        category: str, 
        increment: int = 1, 
        amount: float = 0, 
        tag: Optional[str] = None, 
        record_class: Optional[str] = None,
        note: Optional[str] = None,
        add_type: Optional[bool] = None
    ):
        """
        全域任務掃描器：更新使用者任務進度
        
        :param db: 資料庫 Session
        :param user_id: 使用者 ID
        :param category: 動作類別 (如: '記帳', '系統', '挑戰', 'NT_任務')
        :param increment: 增加的步進數值 (預設 +1)
        :param amount: 交易涉及的金額 (供大額支出或預算任務判定)
        :param tag: 傳入該筆紀錄的標籤 (add_tag)
        :param record_class: 傳入該筆紀錄的分類 (add_class)
        :param note: 傳入該筆紀錄的備註 (add_note)
        :param add_type: 傳入該筆紀錄的類型 (True=收入, False=支出)
        """
        
        # 1. 找出該使用者所有「進行中 (miss_status=1)」的任務
        active_missions = db.query(DailyMission, MissCardsLibrary)\
            .join(MissCardsLibrary, DailyMission.lib_id == MissCardsLibrary.lib_id)\
            .filter(
                DailyMission.user_id == user_id,
                DailyMission.miss_status == 1
            ).all()

        for dm, lib in active_missions:
            # 判斷類別是否匹配 (包含子類別與挑戰)
            is_category_match = (lib.category == category) or (lib.category == '挑戰') or (lib.category.endswith('_任務'))
            
            if is_category_match:
                # --- A. 特定標題的特殊邏輯 ---
                
                # 1. 深度思考：備註心得 > 100 字元
                if lib.title == '深度思考':
                    if note is not None and len(note) > 100:
                        dm.current_val = lib.target_val

                # 2. 意外之財：非固定薪資收入 (非 工資, 獎金, 投資) 且 add_type=True
                elif lib.title == '意外之財':
                    default_income = ['工資', '薪資', '獎金', '投資']
                    if add_type is True and record_class is not None and record_class not in default_income:
                        dm.current_val += increment

                # 3. 自我投資：學習類別支出 (add_type=False)
                elif lib.title == '自我投資':
                    if add_type is False and record_class == '學習':
                        dm.current_val += increment

                # 4. 大膽消費：單筆支出超過 $2000
                elif lib.title == '大膽消費':
                    if add_type is False and amount > 2000:
                        dm.current_val = lib.target_val

                # 5. 享受當下：記錄一筆娛樂支出
                elif lib.title == '享受當下':
                    if add_type is False and record_class == '娛樂':
                        dm.current_val += increment

                # 6. 極限的挑戰：單日總消費加總 <= 100
                elif lib.title == '極限的挑戰':
                    today_total_expense = db.query(func.sum(AddRecord.add_amount)).filter(
                        AddRecord.user_id == user_id,
                        AddRecord.add_date == date.today(),
                        AddRecord.add_type == False
                    ).scalar() or 0
                    if float(today_total_expense) <= 100:
                        dm.current_val = 1
                    else:
                        dm.current_val = 0

                # 7. 客製分類：檢查標籤不在預設名單
                elif lib.title == '客製分類':
                    default_tags = ['需要', '想要', '旅遊']
                    if tag is not None and tag not in default_tags:
                        dm.current_val += increment

                # 8. 大額支出判定 (>= 1000)
                elif lib.title == '大額支出':
                    if amount >= 1000:
                        dm.current_val = lib.target_val 

                # 9. 工作紀錄與人際開銷 (SJ 任務)
                elif lib.title == '工作紀錄' and record_class == '工作':
                    dm.current_val += increment
                elif lib.title == '人際開銷' and record_class == '社交':
                    dm.current_val += increment
                    
                # 🌟 10. 智慧的洞察：AI 聊天觸發 (NT 稀有任務)
                elif lib.title == '智慧的洞察':
                    if category == 'AI_聊天' and note:
                        msg = note.upper()
                        # 判定關鍵字組合：必須有 CPI，且包含「最高」或「指標」
                        if 'CPI' in msg and any(k in msg for k in ['最高', '指標']):
                            dm.current_val = lib.target_val

                # --- B. 一般累進邏輯 (如: 隨手一記、收入進帳等) ---
                else:
                    dm.current_val += increment

                # --- C. 數值保護 ---
                if dm.current_val > lib.target_val:
                    dm.current_val = lib.target_val

        # 執行 commit 將進度寫入資料庫
        db.commit()