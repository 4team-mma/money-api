from pydantic import BaseModel

class GameSummary(BaseModel):
    username: str
    job: str      # 職業/稱號
    level: int    # 等級
    xp: int       # 當前經驗值
    points: int   # 點數/金幣
    
    # 如果你想讓前端好做進度條，可以順便算好「下一級所需經驗」傳回去
    # next_level_xp: int 

    class Config:
        from_attributes = True