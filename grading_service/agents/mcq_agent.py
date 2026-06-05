"""
MCQ Agent — fully deterministic, no LLM call.
Node.js resolves the correct_option_id before calling this service.
"""

from models.request import GradeRequest
from models.response import GradeResponse, FeedbackDetail


def grade_mcq(request: GradeRequest) -> GradeResponse:
    is_correct = (
        request.selected_option_id is not None
        and request.correct_option_id is not None
        and request.selected_option_id == request.correct_option_id
    )

    score = float(request.max_marks) if is_correct else 0.0

    feedback = FeedbackDetail(
        strengths=["Correct answer selected"] if is_correct else [],
        weaknesses=[] if is_correct else ["Incorrect answer selected"],
    )

    return GradeResponse(
        response_id=request.response_id,
        question_id=request.question_id,
        session_id=request.session_id,
        student_id=request.student_id,
        exam_id=request.exam_id,
        score=score,
        max_marks=request.max_marks,
        feedback=feedback,
        confidence=1.0,
        requires_review=False,
        graded_by="ai",
    )
