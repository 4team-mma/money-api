from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ..schemas.feedback import FeedbackResponse, FeedbackCreate
from ..models import Feedback, Member
from ..database import get_db
from ..dependencies import get_current_user

router = APIRouter()

# ===== POST 提交回饋 =====
@router.post(
    "/", 
    response_model=FeedbackResponse,
    summary="提交新的意見回饋",
    description="""
    讓登入使用者針對系統提交意見、Bug回報或功能建議。
    系統會自動抓取使用者 Token 中的身份資訊，並將初始狀態設定為「待處理」。
    """,
    response_description="成功建立回饋記錄並回傳資料內容"
)
def create_feedback(
    data: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    # 將前端傳來的欄位 + 後端抓到的 user_id 組合，並給予初始狀態
    new_feedback = Feedback(
        user_id=current_user.user_id,
        feedback_name=data.feedback_name,
        question_type=data.question_type,
        use_page=data.use_page,
        content=data.content,
        status="待處理"  # 確保資料庫有此欄位
    )

    db.add(new_feedback)
    db.commit()
    db.refresh(new_feedback)
    return new_feedback


# ===== GET 我的回饋 =====
@router.get(
    "/my", 
    response_model=List[FeedbackResponse],
    summary="取得使用者個人的回饋歷史",
    description="取得當前登入使用者過去所有提交過的回饋紀錄，包含處理狀態與提交時間。",
    response_description="回傳該使用者的回饋紀錄列表"
)
def get_my_feedbacks(
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    feedbacks = (
        db.query(Feedback)
        .filter(Feedback.user_id == current_user.user_id)
        .order_by(Feedback.created_at.desc()) # 新增排序，讓最新的顯示在前面
        .all()
    )
    return feedbacks