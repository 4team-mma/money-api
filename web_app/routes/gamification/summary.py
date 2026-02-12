from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from web_app.database import get_db
from web_app.models import Member
from web_app.schemas.gamification import summary as schemas 
from web_app.dependencies import get_current_user
router = APIRouter()

@router.get("/info", response_model=schemas.GameSummary)
def get_game_summary(
    
    current_user: Member=Depends(get_current_user)):
        
    return current_user