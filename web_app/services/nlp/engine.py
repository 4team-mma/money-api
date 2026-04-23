# engine.py
# 這是一個通用的引擎，它不關心規則內容，只負責執行前三項:
# 1.排序規則rule
# 2.先跑hard Rules(強制規則)，命中就return，無視其他規則。
# 3.再跑soft Rules(加分系統)，不會覆蓋,只會加分。
# 4.最後finalize選分數最高
# ctx.trace 是幫助debug用

#from typing import List, Dict
from .context import IntentContext
from .rules import INTENT_RULES

class RuleEngine:
    @staticmethod
    def apply(ctx: IntentContext) -> IntentContext:
        # 按優先級排序
        sorted_rules = sorted(INTENT_RULES, key=lambda x: x["priority"], reverse=True)
        
        # 1. 先跑 Hard Rules (強行攔截)
        for rule in sorted_rules:
            if rule.get("type") == "hard" and rule["when"](ctx):
                ctx.force(rule["target"], rule["name"])
                return ctx # 命中硬規則，直接收工
        
        # 2. 再跑 Soft Rules (累積評分)
        for rule in sorted_rules:
            if rule.get("type") == "soft" and rule["when"](ctx):
                ctx.add_score(rule["target"], rule.get("weight", 0.0), rule["name"])
        
        ctx.finalize()
        return ctx