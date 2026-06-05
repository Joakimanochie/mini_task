from pydantic import BaseModel
from typing import List


class FeedbackDetail(BaseModel):
    strengths: List[str]
    weaknesses: List[str]


class GradeResponse(BaseModel):
    response_id: str
    question_id: str
    session_id: str
    student_id: str
    exam_id: str
    score: float
    max_marks: int
    feedback: FeedbackDetail
    confidence: float
    requires_review: bool
    graded_by: str
