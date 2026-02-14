# web_app/services/game_service.py
from sqlalchemy.orm import Session
from datetime import date
from web_app.models import DailyMission, MissCardsLibrary

class GameService:
    @staticmethod
    def update_mission_progress(db: Session, user_id: int, category: str, increment: int = 1, amount: float = 0):
        """
        全域任務掃描器：更新使用者任務進度
        
        :param db: 資料庫 Session
        :param user_id: 使用者 ID
        :param category: 動作類別 (如: '記帳', '系統', '挑戰', '轉帳', 'SJ_任務')
        :param increment: 增加的步進數值 (預設 +1)
        :param amount: 交易涉及的金額 (供大額支出或預算任務判定)
        
        註：此掃描器不限制 created_at == today，以確保使用者接取的跨日任務能持續累計進度。
        """
        
        # 1. 找出該使用者所有「進行中 (miss_status=1)」的任務
        active_missions = db.query(DailyMission, MissCardsLibrary)\
            .join(MissCardsLibrary, DailyMission.lib_id == MissCardsLibrary.lib_id)\
            .filter(
                DailyMission.user_id == user_id,
                DailyMission.miss_status == 1
            ).all()

        for dm, lib in active_missions:
            # 判斷類別是否匹配：
            # 匹配原則：直接類別相符 OR 屬於挑戰類別 (大額支出等) OR 屬於各性格組標籤 (_任務)
            is_category_match = (lib.category == category) or (lib.category == '挑戰') or (lib.category.endswith('_任務'))
            
            if is_category_match:
                # --- A. 特定標題的特殊邏輯 ---
                
                # 1. 大額支出判定 (要求金額 >= 1000)
                if lib.title == '大額支出':
                    if amount >= 1000:
                        dm.current_val = lib.target_val # 直接標記為達標
                
                # 2. 工具操作判定 (針對 AI 助手詢問等行為)
                elif lib.title == '工具操作':
                    # 每次呼叫增加進度
                    dm.current_val += increment

                # 3. 預算控制判定
                elif lib.title == '預算控制':
                    # 假設 current_val 紀錄的是當次金額或累計金額，此處需配合業務邏輯
                    dm.current_val = int(amount)

                # --- B. 一般累進邏輯 ---
                else:
                    dm.current_val += increment

                # --- C. 數值保護 ---
                if dm.current_val > lib.target_val:
                    dm.current_val = lib.target_val

        # 執行 commit 將進度寫入資料庫
        db.commit()