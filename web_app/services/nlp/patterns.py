# patterns.py
import re

# 意圖偵測專用 Pattern
INTENT_PATTERNS = {
    # 🌟 核心特徵：數字 (用於判斷是否有金額)
    "number": re.compile(r'\d+'),
    "money_unit": re.compile(r'(元|塊|萬|千|張|筆)'),
    
    # 🌟 核心特徵：動作 (妳要求的消費/行為動詞)
    "record_action": re.compile(r'(買|花|吃|喝|付|繳|存|記|入|支|支出|消費|吃了|花了|買了|領|賺|收|薪水|轉|中獎|中了|給|發|得到)'),
    
    "query_trigger": re.compile(r'(多少|剩|總共|統計|分析|餘額|明細|占比|排行|有沒有|吃了沒|買了沒|過|查詢|查一下|找一下|答案|結果|多少錢|算了沒|資產|銀行|存款|台新|可以|夠嗎|夠不夠|評估|能不能|預算查詢)'),
    "advisor_trigger": re.compile(
    r'(健檢|建議|理財顧問|檢視|診斷|投資建議|消費基準|物價|漲價|通膨|cpi|貴|嚴重|指標|薪資競爭力'
    r'|存不到|存不了|消費狀況|消費正不正常|花太多|錢包好扁|變貴|合不合理|消費合理)'
),
    "knowledge_trigger": re.compile(r'(怎麼用|設定|成就|解鎖|規則|什麼是|卡牌|等級|怎麼|如何|手冊)'),
    "doubt_trigger": re.compile(r'(為什麼|怎算的|算錯|不對|為啥|不是吧|提醒|繳費|行事曆|忘記|預算)'),
    "social_greeting": re.compile(r'(你好|早安|午安|下午好|晚安|早上好|謝謝|妙妙|喵|回來了|哈囉|hi|hello|再見|拜拜|辛苦了)'),
    
    # 🌟 新增：金融與股市專屬特徵
    "investment_trigger": re.compile(r'(存股|殖利率|本益比|股息|配息|投資|大盤|etf|走勢|看盤|牛市|熊市|股價)'),
    "stock_keyword": re.compile(r'(台積電|股票|台股|美股|證券)'),
    
    #  Notion 觸發詞！
    "notion_trigger": re.compile(r'(notion|筆記|同步|寫入|整理到)'),
    
    # 🌟 新增：系統與理財的邊界守門員 (Domain Whitelist)
    "domain_keyword": re.compile(r'(系統|手冊|成就|預算|卡牌|等級|任務|理財|記帳|帳戶|設定|介面|Money|喵喵|APP)')
    
}