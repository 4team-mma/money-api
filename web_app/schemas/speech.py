from pydantic import BaseModel

class CorrectionRequest(BaseModel):
    raw_text: str

class CorrectionResponse(BaseModel):
    log_id: int
    raw_text: str
    corrected_text: str
    inference_time_ms: int

# 新增：用來控制開關的 Request 格式
class ToggleRequest(BaseModel):
    enable: bool