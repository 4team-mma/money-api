# web_app/services/advisor_tools.py
import numpy as np
import os
from sqlalchemy.orm import Session
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from ..models.models import Member, AddRecord, CategoryMapping
from ..routes.stats.trends import get_net_worth_history
from sqlalchemy import func, extract, or_, desc
from .gemini_service import GeminiService
from ..prompts.ai_analysis_prompts import CATEGORY_SYSTEM_PROMPT


class FinancialAdvisorService:
    # 定義分類清單，方便維護
    CAT_SOCIAL = {'送禮', '紅包', '請客', '捐款', '聚餐'}
    CAT_GROWTH = {'學習', '課程', '書籍', '教育', '運動', '健身房'}
    CAT_NEEDS = {'房租', '住家', '交通', '帳單', '醫療'}
    CAT_WANTS = {'娛樂', '美甲', 'spa'}
    CAT_FOOD = {'飲食', '餐飲', '早餐', '午餐', '晚餐'}

    @staticmethod
    async def get_smart_dimension(db: Session, class_name: str, user_id: int):
        """
        三層過濾智慧分類器：
        1. 靜態清單匹配
        2. 資料庫 Mapping 表 (個人優先 -> 系統公用)
        3. AI 語意分析 (Fallback)
        """
        # --- Level 1: 靜態清單 (最快) ---
        if class_name in FinancialAdvisorService.CAT_SOCIAL: return "social"
        if class_name in FinancialAdvisorService.CAT_GROWTH: return "growth"
        if class_name in FinancialAdvisorService.CAT_NEEDS: return "needs"
        if class_name in FinancialAdvisorService.CAT_WANTS: return "wants"
        if class_name in ['飲食', '餐飲']: return "food"

        # --- Level 2: 資料庫洋蔥式查詢 ---
        # 同時找該使用者的私藏標籤 或 系統公用標籤
        mapping = (
            db.query(CategoryMapping)
            .filter(
                CategoryMapping.user_input == class_name,
                or_(CategoryMapping.user_id == user_id, CategoryMapping.user_id.is_(None)) # 使用 .is_(None)
                )
            .order_by(desc(CategoryMapping.user_id))
            .first()
            )

        if mapping:
            return mapping.dimension

        # --- Level 3: 呼叫 AI (Gemini) ---
        # 這裡會用到我們之前討論的專屬分類 Prompt
        try:
            # 構造一個超簡單的問句給 Gemini
            predict_prompt = f"請將『{class_name}』分類為以下四種維度之一：growth, needs, wants, social。只需回傳代碼。"
            
            # 這裡呼叫 Gemini (API Key 用妳路由那套邏輯抓取)
            env_key = os.getenv("GEMINI_API_KEY")
            ai_res = await GeminiService.chat_async(
                api_key=str(env_key),
                model_id="gemini-1.5-flash",
                prompt=predict_prompt,
                system_instruction=CATEGORY_SYSTEM_PROMPT # 專門用來教它分類的指令
            )
            
            # 取得 AI 回傳的字串並整理 (預防它回傳多餘空格或大寫)
            ai_dim = ai_res.get("text", "wants").strip().lower()
            
            # 驗證 AI 回傳是否在我們定義的範圍內
            valid_dims = ["growth", "needs", "wants", "social"]
            if ai_dim not in valid_dims:
                ai_dim = "wants" # 萬一 AI 亂回答，給個保險值

            # 存入資料庫作為「全局公用」快取 (user_id=None)
            new_cache = CategoryMapping(
                user_id=None,
                user_input=class_name,
                dimension=ai_dim,
                is_ai_generated=True
            )
            db.add(new_cache)
            db.commit()
            return ai_dim

        except Exception as e:
            print(f"AI 分類預測失敗: {e}")
            return "other"

    @staticmethod
    async def _categorize_expenses(db: Session, expenses: list, user_id: int):
        # 1. 先初始化 sums（在迴圈外面）
        sums = {"growth": 0.0, "social": 0.0, "needs": 0.0, "wants": 0.0, "food": 0.0, "other": 0.0}

        # 2. 迴圈裡面才有 dim
        for r in expenses:
            amount = float(r.add_amount)
            if r.add_member != "自己":
                sums["social"] += amount
                continue

            dim = await FinancialAdvisorService.get_smart_dimension(db, r.add_class, user_id)

            if dim == "food":
                sums["food"] += amount
            elif dim in sums:
                sums[dim] += amount
            else:
                sums["other"] += amount
        return sums

    @staticmethod
    async def _get_monthly_history(db: Session, user_id: int, count: int):
        """抓取過去 N 個月同日期以前的消費總額"""
        today = date.today()
        current_day = today.day
        first_day_this_month = today.replace(day=1)
        start_date = first_day_this_month - relativedelta(months=count)

        history_data = (
            db.query(func.sum(AddRecord.add_amount).label('total'))
            .filter(
                AddRecord.user_id == user_id,
                AddRecord.add_type.is_(False),
                AddRecord.add_date >= start_date,
                AddRecord.add_date < first_day_this_month,
                extract('day', AddRecord.add_date) <= current_day
            )
            # 先依照年份與月份分組
            .group_by(extract('year', AddRecord.add_date), extract('month', AddRecord.add_date))
            # 接著進行降冪排序，確保最新的月份排在第一筆
            .order_by(
                desc(extract('year', AddRecord.add_date)), 
                desc(extract('month', AddRecord.add_date))
            )
            .all()
        )
        return [float(row.total) for row in history_data]

    @staticmethod
    def _calculate_z_score_anomaly(current_val: float, history_vals: list, threshold: float = 2.0):
        """Z-score 異常偵測"""
        if len(history_vals) < 3:
            return {"is_detected": False, "z_score": 0, "severity": "normal"}
        data = np.array(history_vals)
        mean, std = np.mean(data), np.std(data)
        if std == 0: return {"is_detected": False, "z_score": 0, "severity": "normal"}
        z_score = (current_val - mean) / std
        return {
            "is_detected": bool(abs(z_score) > threshold),
            "z_score": round(float(z_score), 2),
            "severity": "high" if abs(z_score) > 3 else "medium" if abs(z_score) > threshold else "normal"
        }

    @staticmethod
    async def get_ai_context(db: Session, user: Member):
        """主入口：數據成熟度檢查 + 深度財務分析"""
        today = date.today()
        
        # --- 1. 安檢門：數據成熟度校驗 (妳的 90天/80% 規則) ---
        register_days = (today - user.created_at.date()).days
        unique_days_count = db.query(func.count(func.distinct(AddRecord.add_date))).filter(
            AddRecord.user_id == user.user_id,
            AddRecord.add_type.is_(False)
        ).scalar()

        denominator = min(register_days, 90)
        density = unique_days_count / denominator if denominator > 0 else 0

        # 若未達門檻，回傳格式讓前端顯示「解鎖中」狀態
        if register_days < 90 or density < 0.8:
            return {
                "is_unlocked": False,
                "user_profile": {"name": user.name},
                "status": {
                    "register_days": register_days,
                    "density": f"{density:.1%}",
                    "days_needed": max(0, 90 - register_days),
                },
                "message": f"Hi {user.name}，你這段時間的記帳習慣（密度：{density:.1%}）我都有看在眼裡。目前的數據像是一幅還沒完成的畫，再給我一點時間觀察你的規律，當你達成 90 天的累積後，我將為你揭曉專屬於你的財務洞察分析！"
            }

        # --- 2. 資料獲取與前處理 (已達標者執行) ---
        this_month_start = today.replace(day=1)
        ninety_days_ago = today - timedelta(days=90)
        last_month_start = this_month_start - relativedelta(months=1)
        last_month_end = this_month_start - timedelta(days=1)

        all_records = db.query(AddRecord).filter(
            AddRecord.user_id == user.user_id,
            AddRecord.add_date >= ninety_days_ago
        ).all()

        income_list = [float(r.add_amount) for r in all_records if r.add_type]
        expenses_90d = [r for r in all_records if not r.add_type]

        total_90d_income = sum(income_list) if income_list else 0
        total_cur_month = sum(float(r.add_amount) for r in expenses_90d if r.add_date >= this_month_start)
        total_past_month = sum(float(r.add_amount) for r in expenses_90d if last_month_start <= r.add_date <= last_month_end)
        safe_income = total_90d_income if total_90d_income > 0 else 1
        
        # 抓取淨資產
        net_worth_data = get_net_worth_history(db, user)
        current_net_worth = net_worth_data['monthly'][0]['net'] if net_worth_data['monthly'] else 0

        # --- 3. 四大維度分類與異常分析 ---
        sums = await FinancialAdvisorService._categorize_expenses(db, expenses_90d, user.user_id)
        
        # 抓取MTD歷史數據 (滿 6 個月才執行)
        history_real = await FinancialAdvisorService._get_monthly_history(db, user.user_id, 6)
        
        # 1. 取得上個月同期的數據 (MTD)
        # 既然 history_real 是由近到遠，第一筆就是上個月同期
        total_past_month_mtd = history_real[0] if history_real else 0
        growth_rate_month = (total_cur_month - total_past_month_mtd) / total_past_month_mtd if total_past_month_mtd > 0 else 0

        # 3. 執行異常偵測_Zscore
        anomaly_results = {"is_detected": False, "z_score": 0, "severity": "normal", "direction": "穩定"}
        anomaly_description = "正在建立您的財務慣性模型"
        direction = "穩定"

        if len(history_real) >= 6:
            if total_cur_month == 0:
                anomaly_description = "本月尚未有記帳資料"
            else:
                calculated_res = FinancialAdvisorService._calculate_z_score_anomaly(total_cur_month, history_real)
                if calculated_res:
                    anomaly_results = calculated_res
                    z = anomaly_results.get('z_score', 0)
                    direction = "激增" if z > 0 else "銳減" if z < 0 else "穩定"
                    anomaly_description = f"{anomaly_results.get('severity')} ({direction})"
                else:
                    anomaly_description = "正在建立您的財務慣性模型"

        res = anomaly_results

        # 4. 封裝數據
        summary = {
            "current_month_total": total_cur_month,
            "month_on_month_growth": f"{growth_rate_month:.1%}",
            "net_worth": current_net_worth, # 淨資產現在順利入庫了！
            "anomaly_analysis": {
                "is_detected": res.get("is_detected", False),
                "z_score": res.get("z_score", 0),
                # 使用我們在第 3 步根據數據成熟度預處理好的描述文字
                "severity": anomaly_description, 
                # 只有在偵測到異常時才顯示方向，否則維持穩定，避免 MoM 小波動誤導語氣
                "direction": direction if res.get("is_detected") else "穩定"
            }
        }

        # --- 消費結構分析 (對應 Prompt 的 struct_str) ---
        analysis_total_90d = sum([sums["growth"], sums["social"], sums["needs"], sums["wants"], sums["food"]])
        display_names = {"growth": "成長動能", "social": "人際支出", "needs": "生活剛需", "wants": "生活品味", 'food':'飲食消費'}
        consumption_analysis = {}
        for key, label in display_names.items():
            ratio = sums[key] / analysis_total_90d if analysis_total_90d > 0 else 0
            consumption_analysis[key] = {
                "label": label,
                "percentage": f"{ratio:.1%}",
                "monthly_avg": round(sums[key] / 3)
            }

        # --- 最終回傳：結構完全對準妳的 Prompt 函式 ---
        return {
            "is_unlocked": True,
            "user_profile": {"name": user.name},
            "consumption_structure": consumption_analysis,
            "financial_summary": summary,
            "lifestyle_metrics": {
                "financial_stress": float(sums["needs"]) / safe_income,
                "growth_investment": float(sums["growth"]) / safe_income,
                "food_ratio": float(sums["food"]) / safe_income,
                "exquisiteness_ratio": float(sums["wants"]) / (sums["wants"] + sums["needs"]) if (sums["wants"] + sums["needs"]) > 0 else 0,
                "social_ratio": float(sums["social"]) / safe_income,
                "future_investment_ratio": float(sums["growth"]) / (sums["growth"] + sums["wants"]) if (sums["growth"] + sums["wants"]) > 0 else 0
            },
            "monthly_avg_90d": {k: float(v / 3) for k, v in sums.items() if k != "other"}
        }