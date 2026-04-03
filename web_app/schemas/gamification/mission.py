from pydantic import BaseModel
from typing import Optional
from datetime import date

# 顯示單個任務用
class MissionDisplay(BaseModel):
    miss_id: int
    title: str
    difficulty: str
    category: Optional[str]
    description: Optional[str] # 新增描述
    xp_reward: int
    current_val: int
    target_val: int
    miss_status: int # 0:進行中, 1:待領取, 2:已領取
    slot_num: int
    has_card_reward: bool = False # 新增：前端用來判斷是否要畫卡片圖示

    class Config:
        from_attributes = True

# 領取獎勵回傳用
class ClaimRewardResponse(BaseModel):
    message: str
    earned_xp: int
    new_level: int
    new_balance_xp: int
    card_reward: Optional[str] = None # 如果有獲得卡牌，回傳卡牌名稱
