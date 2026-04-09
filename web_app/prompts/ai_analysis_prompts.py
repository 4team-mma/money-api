# 1. 補上這一段（這就是 AI 的「靈魂/人設」）
SYSTEM_INSTRUCTION = """
你是一位具備臨床心理學洞察力與精準數據分析能力的 AI 財務顧問。
你深知數字背後代表的是使用者的焦慮、慾望與夢想。
你的溝通風格：
1. 不說教：不使用責備語氣，而是從數據中找出『生活失衡』的訊號。
2. 專業轉譯：能將複雜的統計指標（如 Z-Score）轉譯成溫暖、好懂的生活建議。
3. 重視成長：比起單純存錢，你更鼓勵使用者將資源投入在能產生複利效應的『自我成長』上。
"""

def get_financial_analysis_prompt(data: dict):
    # 使用 .get() 確保即使資料結構有缺，也不會直接掛掉
    metrics = data.get('metrics', {})
    anomaly = metrics.get('anomaly_analysis', {"is_anomaly": False, "z_score": 0})
    user_profile = data.get('user_profile', {"name": "使用者", "job": "職場新秀"})
    top_cats = data.get('top_categories', [])
    
    # 建立異常狀況描述
    anomaly_text = "【異常偵測：正常】"
    if anomaly.get('is_anomaly'):
        severity_map = {"high": "顯著異常 (強烈警示)", "medium": "輕微波動 (溫馨提醒)"}
        anomaly_text = (
            f"【異常偵測：{severity_map.get(anomaly.get('severity'), '注意')}】\n"
            f"- 偏離常態程度 (Z-Score): {anomaly.get('z_score')}\n"
            f"- 警示：本月支出行為與過去規律不符，需檢視單筆大額開銷。"
        )

    # 處理分類字串，若無資料則顯示「尚無分類數據」
    categories_str = ', '.join([f"{i['category']}({i['ratio']}%)" for i in top_cats]) if top_cats else "尚無分類數據"

    return f"""
    作為理財顧問，請分析以下數據：
    
    【基本數據】
    - 使用者：{user_profile['name']} (職業: {user_profile['job']})
    - 本月總支出：NT$ {metrics.get('total_expense', 0):,}
    - 支出變動率：{metrics.get('growth_from_last_month', '0%')}
    - 目前淨資產：NT$ {metrics.get('current_net_worth', 0):,}
    - 消費分佈：{categories_str}
    
    {anomaly_text}
    
    【分析任務】
    1. 結合 Z-Score 異常狀態：若為異常，請運用心理學中的「損失規避」心理引導使用者檢視開支；若正常，請給予正向增強。
    2. 職業化建議：根據職業背景，提供一項能提升「長期價值」而非僅是「節省」的行動方案。
    3. 字數：150字內，口吻要像一位懂數據、也懂生活的智者。
    """