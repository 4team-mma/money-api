# rules.py
# 這裡只放「規則的定義」。可輕鬆地調整 priority 權重。
# Declarative Rule System

INTENT_RULES = [
{
    "name": "NOTION_WRITE_DETECT",
    "priority": 120,
    "type": "hard",
    "when": lambda c: c.has("notion_trigger") and (
        "寫入" in c.text or "存到" in c.text or "notion" in c.text.lower()
    ),
    "target": "NOTION_WRITE"
},
    # 🔴 Hard Rules (第一優先：絕對法則，命中即強制決定)
    {
        "name": "ADVISOR_HARD_PROTECT",
        "priority": 110,
        "type": "hard",
        # 🌟 核心修正：如果小主人問「什麼是」、「解釋」、「意思」，代表在問知識，不准攔截！
        "when": lambda c: c.has("advisor_trigger") and not any(kw in c.text for kw in ["什麼是", "解釋", "意思", "定義"]), 
        "target": "ADVISOR"
    },
    {
        "name": "KNOWLEDGE_HARD_PROTECT",
        "priority": 100,
        "type": "hard",
        "when": lambda c: c.has("knowledge_trigger") and not c.has("social_greeting"),
        "target": "KNOWLEDGE"
    },
    
    # 🌟 新增：投資顧問專屬硬攔截
    {
        "name": "INVESTMENT_HARD_PROTECT",
        "priority": 105,
        "type": "hard",
        # 🛡️ 雙重精密濾網：
        # 1. 只要出現強烈分析意圖 (存股/殖利率/本益比) -> 絕對是理財顧問
        # 2. 出現股票實體名詞 (台積電)，且帶有查詢/諮詢意味 (幫我看/建議/查) -> 理財顧問
        # 這樣寫能完美放行「我今天買股票花了五萬」這類句子進入下方的 RECORD 防線
        "when": lambda c: c.has("investment_trigger") or (
            c.has("stock_keyword") and (c.has("advisor_trigger") or c.has("query_trigger") or "看" in c.text)
        ),
        "target": "ADVISOR"
    },
    
    {
        "name": "ABSOLUTE_RECORD_PROTECT",
        "priority": 98,  # 🌟 優先級極高，幾乎凌駕所有猜測
        "type": "hard",
        # 🛡️ 鐵律：只要有「數字」+「動作(吃/買/花)」+「金額單位(元/塊)」
        # 且沒有明確的查詢動詞(查/多少)，就絕對是記帳！
        "when": lambda c: (
            c.has("number") and 
            c.has("record_action") and 
            c.has("money_unit") and 
            "多少" not in c.text and 
            "查" not in c.text
        ),
        "target": "RECORD"
    },
    # rules.py 節錄 (請替換原本的 RECORD_VIOLENT_INTERCEPT)

    # ---------------------------------------------------------
    # 🌟 核心進化：將暴力攔截拆分為兩道精密濾網 (Priority 96 與 95)
    # ---------------------------------------------------------

    {
        "name": "RECORD_INTERCEPT_TO_QUERY",
        "priority": 96,  # 優先級 96，比 95 先執行
        "type": "hard",
        # 第一道濾網：ONNX 猜記帳，但沒數字。不過有「多少/查/有沒有」等疑問詞！
        "when": lambda c: c.initial_intent in ["RECORD", "MULTI_RECORD"] and not c.has("number") and (
            c.has("query_trigger") or c.has("doubt_trigger") or "多少" in c.text or "查" in c.text
        ),
        "target": "QUERY"
    },
    {
        "name": "RECORD_INTERCEPT_TO_CHAT",
        "priority": 95,  # 優先級 95，最後的保底防線
        "type": "hard",
        # 第二道濾網：ONNX 猜記帳，沒疑問詞，且 (沒動作 或 沒數字) -> 這才是真正的純閒聊或廢話
        "when": lambda c: c.initial_intent in ["RECORD", "MULTI_RECORD"] and (not c.has("record_action") or not c.has("number")),
        "target": "CHAT"
    },

    # ---------------------------------------------------------

    
    
    # 🟡 Soft Rules (第二優先：加分制)
    
    {
        "name": "SOCIAL_GREETING_RESCUE",
        "priority": 90,
        "type": "soft",
        # 修改前：只排除了記帳(數字+動詞)，卻忘記排除查詢(多少/有沒有)
        # "when": lambda c: c.has("social_greeting") and not (c.has("record_action") and c.has("number")),
        
        # 🌟 修改後：如果句子有明確的「查詢觸發詞」或「疑問詞」，招呼語就不能加分！
        "when": lambda c: c.has("social_greeting") and not (
            (c.has("record_action") and c.has("number")) or 
            c.has("query_trigger") or 
            c.has("doubt_trigger")
        ),
        "target": "CHAT",
        "weight": 2.5
    },
    {
        "name": "RECORD_UPGRADE",
        "priority": 80,
        "type": "soft",
        "when": lambda c: c.has("number") and c.has("record_action"),
        "target": "RECORD",
        "weight": 2.0
    },
    {
        "name": "QUERY_DOUBT_UPGRADE",
        "priority": 70,
        "type": "soft",
        "when": lambda c: c.has("doubt_trigger") or c.has("query_trigger"),
        "target": "QUERY",
        "weight": 1.5
    }
]