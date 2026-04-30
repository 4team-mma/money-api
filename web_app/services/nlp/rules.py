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
        "when": lambda c: c.has("advisor_trigger"), 
        "target": "ADVISOR"
    },
    {
        "name": "KNOWLEDGE_HARD_PROTECT",
        "priority": 100,
        "type": "hard",
        "when": lambda c: c.has("knowledge_trigger") and not c.has("social_greeting"),
        "target": "KNOWLEDGE"
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
    {
        "name": "RECORD_VIOLENT_INTERCEPT", # 🌟 妳的核心進化邏輯：暴力攔截
        "priority": 95,
        "type": "hard",
        # 條件：如果 ONNX 猜記帳，但符合以下任一條件則降級：
        # 1. 沒有動作動詞 (not c.has("record_action"))
        # 2. 沒有具體金額數字 (not c.has("number"))
        "when": lambda c: c.initial_intent in ["RECORD", "MULTI_RECORD"] and (not c.has("record_action") or not c.has("number")),
        "target": "CHAT"
    },

    
    
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