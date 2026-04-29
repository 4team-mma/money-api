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
        # 只有在「不是標準記帳(動詞+數字)」的情況下，招呼語才出來救援 CHAT
        "when": lambda c: c.has("social_greeting") and not (c.has("record_action") and c.has("number")),
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