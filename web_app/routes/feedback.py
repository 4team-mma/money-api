from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import datetime

from ..schemas.feedback import FeedbackResponse, FeedbackCreate, FeedbackAdminReply
from ..models import Feedback, Member
from ..database import get_db
from ..dependencies import get_current_user # 假設這裡會驗證 Token

router = APIRouter()

# 2===== [管理者專用] 取得所有回饋列表 =====
@router.get(
    "/all",
    response_model=List[FeedbackResponse],
    summary="管理端：取得系統所有回饋",
    description="取得所有使用者的回饋，並透過 joinedload 抓取使用者資訊（如用戶名、Email）。"
)
def get_all_feedbacks(
    db: Session = Depends(get_db),
    # current_user: Member = Depends(get_admin_user) # 實務上建議加一個管理者權限驗證
):
    # 使用 joinedload 確保 user 物件被載入，對應 Schema 中的 UserSimpleInfo
    feedbacks = (
        db.query(Feedback)
        .options(joinedload(Feedback.user))
        .order_by(Feedback.created_at.desc())
        .all()
    )
    return feedbacks


# 3===== [管理者專用] 更新回饋狀態 (下拉選單觸發) =====
@router.patch(
    "/{feedback_id}",
    response_model=FeedbackResponse,
    summary="管理端：更新回饋處理狀態",
    description="更新 is_replied (0, 1, 2) 或填寫 admin_answer。"
)
def update_feedback_admin(
    feedback_id: int,
    data: FeedbackAdminReply,
    db: Session = Depends(get_db)
):
    # 這裡記得也要載入 user 資訊，否則回傳 FeedbackResponse 時會噴錯
    feedback = (
        db.query(Feedback)
        .options(joinedload(Feedback.user))
        .filter(Feedback.feedback_id == feedback_id)
        .first()
    )

    if not feedback:
        raise HTTPException(status_code=404, detail="找不到該回饋紀錄")

    # 更新狀態 (0=待處理, 1=處理中, 2=已解決)
    feedback.is_replied = data.is_replied

    # 如果有填寫回覆內容
    if data.admin_answer is not None:
        feedback.admin_answer = data.admin_answer
        feedback.replied_at = datetime.now() # 紀錄回覆時間
        # 💡 如果有填內容，通常自動設為「已解決 (2)」是很合理的 UI 邏輯
        if feedback.is_replied == 0:
            feedback.is_replied = 2

    db.commit()
    db.refresh(feedback)
    return feedback


# 1===== [一般用戶] 提交新回饋 =====
@router.post(
    "/",
    response_model=FeedbackResponse,
    summary="提交新的意見回饋"
)
def create_feedback(
    data: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    new_feedback = Feedback(
        user_id=current_user.user_id,
        feedback_name=data.feedback_name,
        question_type=data.question_type,
        use_page=data.use_page,
        content=data.content,
        is_replied=0  # 💡 統一使用 int 狀態：0 = 待處理
    )

    db.add(new_feedback)
    db.commit()
    db.refresh(new_feedback)
    return new_feedback


# 4===== [一般用戶] 取得個人歷史 =====
@router.get(
    "/my",
    response_model=List[FeedbackResponse],
    summary="取得使用者個人的回饋歷史"
)
def get_my_feedbacks(
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    return (
        db.query(Feedback)
        .filter(Feedback.user_id == current_user.user_id)
        .order_by(Feedback.created_at.desc())
        .all()
    )
