from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ..schemas.feedback import FeedbackResponse ,FeedbackCreate
from ..models import Feedback,Member
from ..database import get_db
from ..dependencies import get_current_user

router = APIRouter()

@router.post("/", response_model=FeedbackResponse)
def create_feedback(
    data: FeedbackCreate,

    db: Session = Depends(get_db),

    # 這裡會從 Token 自動抓取 user_id，不需要前端傳

    current_user: Member = Depends(get_current_user)

):

# 將前端傳來的 4 個欄位 + 後端抓到的 user_id 組合起來
  new_feedback = Feedback(
  user_id=current_user.user_id,
  feedback_name=data.feedback_name,
  question_type=data.question_type,
  use_page=data.use_page,
  content=data.content
  ) 

  db.add(new_feedback)
  db.commit()
  db.refresh(new_feedback)
  return new_feedback

@router.get("/my", response_model=List[FeedbackResponse])
def get_my_feedbacks(
  db: Session = Depends(get_db),
  current_user: Member = Depends(get_current_user)
):

  """
  讓使用者查看自己過往提交的意見回饋
  """

  feedbacks = db.query(Feedback).filter(Feedback.user_id == current_user.user_id).all()
  return feedbacks