# 這裡只放「規則的定義」。可輕鬆地調整 priority 權重。
# Declarative Rule System


# 定義規則清單
# priority 越高越先執行
INTENT_RULES = [
    # 🔴 Hard Rules (一旦命中，直接決定結果，不玩加分)
    {
        "name": "KNOWLEDGE_HARD_PROTECT",
        "priority": 100,
        "type": "hard",
        "when": lambda c: c.has("knowledge_trigger") and not c.has("social_greeting"),
        "target": "KNOWLEDGE"
    },
    
    # 🟡 Soft Rules (根據特徵加分，最後算總分)
    {
        "name": "SOCIAL_GREETING_RESCUE",
        "priority": 90,
        "type": "soft",
        "when": lambda c: c.has("social_greeting"),
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