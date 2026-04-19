# 負責把原始訊息轉化成「結構化特徵」，是系統的「感官」。


from .patterns import INTENT_PATTERNS

class IntentContext:
    def __init__(self, text: str, initial_intent: str, initial_confidence: float = 1.0):
        self.text = text
        self.initial_intent = initial_intent
        self.intent = initial_intent
        self.trace = []
        # 初始化分數池
        self.scores = {"CHAT": 0.0, "RECORD": 0.0, "QUERY": 0.0, "ADVISOR": 0.0, "KNOWLEDGE": 0.0}
        self.scores[initial_intent] = initial_confidence
        
        self.features = {key: bool(pattern.search(text)) for key, pattern in INTENT_PATTERNS.items()}

    def add_score(self, intent: str, weight: float, rule_name: str):
        if intent in self.scores:
            self.scores[intent] += weight
            self.trace.append(f"[{rule_name}] {intent} +{weight}")

    def force(self, intent: str, rule_name: str):
        self.intent = intent
        self.trace.append(f"⚡ [HARD_RULE: {rule_name}] -> {intent}")

    def has(self, name: str) -> bool:
        return self.features.get(name, False)

    def finalize(self):
        if not self.scores:
            return self.intent
        # 結算最高分
        self.intent = max(self.scores, key=lambda k: self.scores[k])
        return self.intent