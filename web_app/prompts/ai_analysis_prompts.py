def get_financial_analysis_prompt(data: dict):
    return f"""
    作為理財顧問，請分析以下數據並給出建議：

    【財務數據】
    - 使用者：{data['user_profile']['name']} (職業: {data['user_profile']['job']})
    - 本月總支出：NT$ {data['metrics']['total_expense']:,}
    - 支出變動率：{data['metrics']['growth_from_last_month']}
    - 目前淨資產：NT$ {data['metrics']['current_net_worth']:,}
    - 前三大支出項目：{', '.join([f"{i['category']}({i['ratio']}%)" for i in data['top_categories']])}

    【分析要求】
    1. 如果變動率 > 15%，請特別提醒異常並分析原因。
    2. 結合職業背景給出一條具體的行動建議。
    3. 語氣要親切且專業，總字數控制在 150 字內。
    """

SYSTEM_INSTRUCTION = "你是一位精通數據分析與心理學的 AI 理財顧問，擅長從枯燥數字中發現生活品質的平衡點。"
