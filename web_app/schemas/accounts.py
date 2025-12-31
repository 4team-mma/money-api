from pydantic import BaseModel
class AccountResponse(BaseModel):
    account_name: str
    current_balance: float