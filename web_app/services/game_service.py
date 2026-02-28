# web_app/services/game_service.py
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from typing import Optional
from web_app.models import DailyMission, MissCardsLibrary, AddRecord,Account
from web_app.models import Member

class GameService:
    @staticmethod
    def get_required_xp(level: int) -> int:
        """
        計算該等級升級所需的總 XP (階層式公式)
        """
        if level < 10: return 100 + (level * 20)
        if level < 20: return 300 + (level * 30)
        if level < 50: return 1000 + (level * 50)
        if level < 100: return 3000 + (level * 100)
        return 10000

    @staticmethod
    def add_user_xp(db: Session, user: Member, xp_to_add: int):
        """
        替使用者增加經驗值，並處理自動升級邏輯 (支援連續跳級)
        """
        # 確保初始數值不是 None
        if user.xp is None: user.xp = 0
        if user.level is None: user.level = 1
        
        user.xp += xp_to_add
        
        # 溢位升級判斷
        while True:
            required = GameService.get_required_xp(user.level)
            
            # 如果目前經驗值超過門檻，且尚未達到等級上限
            if user.xp >= required and user.level < 100:
                user.xp -= required  # 扣除升級消耗，剩餘 XP 繼續累積
                user.level += 1      # 等級加 1
            else:
                # XP 不足或已滿級，停止判斷
                break
        
        # 這裡不需要 db.commit()，由呼叫此 Service 的 Router 決定何時 commit
        db.add(user)
        return user
    
    @staticmethod
    def check_end_of_day_missions(db: Session, user_id: int):
        """
        結算判定：檢查所有需要到晚上或結算時點才能判定的任務
        如：預算控制、節能減碳 (交通支出)
        """
        #now = datetime.now()
        # 只要超過 23:00 或是手動觸發結算邏輯
        # 這裡我們設定只要調用就檢查，但你也可以加 if now.hour >= 23:
        
        today = date.today()
        active_missions = db.query(DailyMission, MissCardsLibrary)\
            .join(MissCardsLibrary, DailyMission.lib_id == MissCardsLibrary.lib_id)\
            .filter(
                DailyMission.user_id == user_id,
                DailyMission.miss_status == 1,
                DailyMission.created_at == today
            ).all()

        for dm, lib in active_missions:
            # 1. 預算控制：今日總支出控制在 $500 以內
            if lib.title == '預算控制':
                total_exp = db.query(func.sum(AddRecord.add_amount)).filter(
                    AddRecord.user_id == user_id,
                    AddRecord.add_date == today,
                    AddRecord.add_type == False
                ).scalar() or 0
                
                if float(total_exp) <= 500:
                    dm.current_val = lib.target_val # 500/500 完成
                else:
                    dm.current_val = 0 # 失敗或重置

            # 2. 節能減碳：今日交通類總消費不超過 $100
            elif lib.title == '節能減碳':
                traffic_exp = db.query(func.sum(AddRecord.add_amount)).filter(
                    AddRecord.user_id == user_id,
                    AddRecord.add_date == today,
                    AddRecord.add_type == False,
                    AddRecord.add_class == '交通' # 確保你的分類名稱正確
                ).scalar() or 0
                
                if float(traffic_exp) <= 100:
                    dm.current_val = lib.target_val # 100/100 完成
                else:
                    dm.current_val = 0
            
            # 🌟 新增 3. 減少外食：今日飲食類消費不超過 $300
            elif lib.title == '減少外食':
                food_exp = db.query(func.sum(AddRecord.add_amount)).filter(
                AddRecord.user_id == user_id,
                AddRecord.add_date == today,
                AddRecord.add_type == False,
                AddRecord.add_class == '飲食' # ⚠️ 請確認你資料庫定義的分類名稱是「飲食」
            ).scalar() or 0
            
            # 如果整天吃不到 300，進度填滿 (1/1 或 300/300)
            # 根據你 SQL 的 target_val 是 300，我們把 current_val 設為 300 表示達成
            if float(food_exp) <= 300:
                dm.current_val = lib.target_val 
            else:
                dm.current_val = 0 # 超過就失敗
            
            # 🌟 新增 4. 無現金支付判定
            if lib.title == '無現金支付':
            # 找出今天該使用者的所有支出紀錄 (add_type=False)
                records = db.query(AddRecord).filter(
                    AddRecord.user_id == user_id,
                    AddRecord.add_date == today,
                    AddRecord.add_type == False
            ).all()

            if not records:
                # 如果今天完全沒消費，依據你的設計決定是否算達成。通常建議沒消費也算守住紀錄。
                dm.current_val = 0 
                continue

            # 檢查這些紀錄所屬的帳戶類型
            all_credit = True
            for r in records:
                acc = db.query(Account).filter(Account.account_id == r.account_id).first()
                if not acc or acc.account_type != 'credit': # 只要有一筆不是 credit
                    all_credit = False
                    break
            
            if all_credit:
                dm.current_val = lib.target_val # 達成 1/1
            else:
                dm.current_val = 0 # 只要有一筆非信用卡消費，進度歸零
            
            

        db.commit()
    

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
                    
                # 10. 智慧的洞察：AI 聊天觸發 (NT 稀有任務)
                elif lib.title == '智慧的洞察':
                    if category == 'AI_聊天' and note:
                        msg = note.upper()
                        # 判定關鍵字組合：必須有 CPI，且包含「最高」或「指標」
                        if 'CPI' in msg and any(k in msg for k in ['最高', '指標']):
                            dm.current_val = lib.target_val
                            
                # 11. 宏觀分析：年度報表匯出 (NF 任務)
                elif lib.title == '宏觀分析':
                    # 只要類別匹配成功（由 API 傳入 '宏觀分析'），就直接加 1
                    if category == '宏觀分析':
                        dm.current_val += increment
                
                # 12. 雙向標籤：任務判斷
                if lib.title == '雙向標籤':
                    if tag:
                        # 假設標籤在資料庫中是以逗點分隔儲存，例如 "需要,自訂標籤1"
                        # 我們先將字串拆解成清單
                        tag_list = [t.strip() for t in tag.split(',') if t.strip()]
                        
                        # 判定條件：
                        # 1. 標籤總數至少要 2 個
                        # 2. 且其中至少有一個不屬於預設名單（自訂標籤）
                        default_tags = ['需要', '想要', '旅遊']
                        custom_tags = [t for t in tag_list if t not in default_tags]
                        
                        # 如果標籤總數 >= 2 且包含自訂標籤
                        if len(tag_list) >= 2 and len(custom_tags) >= 1:
                            dm.current_val = lib.target_val # 達成任務
                    continue # 處理完畢跳過後續邏輯
                
                
                
                
                # --- B. 一般累進邏輯 (如: 隨手一記、收入進帳等) ---
                else:
                    # 優化：記帳達人或類似任務，通常指「花費紀錄」
                    if lib.title == '記帳達人':
                        if add_type is False: # 僅限支出才累加
                            dm.current_val += increment
                    
                    # 優化：資金調度任務判定
                    elif lib.title == '資金調度':
                        if category == '轉帳': # 確保只有從 transfers.py 來的才算
                            dm.current_val += increment
                            
                    else:
                        # 其他一般任務（如隨手一記）維持現狀
                        # 排除需要晚間結算的任務標題
                        nightly_tasks = ['預算控制', '減少外食', '節能減碳', '無現金支付']
                        if lib.title not in nightly_tasks:
                            dm.current_val += increment

                # --- C. 數值保護 ---
                if dm.current_val > lib.target_val:
                    dm.current_val = lib.target_val

        # 執行 commit 將進度寫入資料庫
        db.commit()
        
