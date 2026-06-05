"""
Main grading endpoint.
Receives a grading request from Node.js,
routes to the correct agent based on question_type,
returns a structured GradeResponse.
"""

from fastapi import APIRouter, HTTPException
from models.request import GradeRequest
from models.response import GradeResponse, FeedbackDetail
from agents.mcq_agent import grade_mcq
from agents.theory_agent import grade_theory
from agents.handwritten_agent import grade_handwritten
from agents.diagram_agent import grade_diagram

router = APIRouter()


@router.post("/grade", response_model=GradeResponse)
async def grade(request: GradeRequest) -> GradeResponse:
    """
    Grading endpoint called by Node.js backend.
    Node.js calls this once per question_id, in order,
    until all responses under a session are graded.
    """
    question_type = request.question_type

    try:
        if question_type == "mcq":
            return grade_mcq(request)

        elif question_type == "theory":
            if not request.student_text:
                return _empty_response(request)
            return grade_theory(request)

        elif question_type == "handwritten":
            if not request.student_image_url:
                return _empty_response(request)
            return await grade_handwritten(request)

        elif question_type == "diagram":
            if not request.student_image_url:
                return _empty_response(request)
            return await grade_diagram(request)

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown question_type: {question_type}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Grading failed for question {request.question_id}: {str(e)}"
        )


def _empty_response(request: GradeRequest) -> GradeResponse:
    """Returns a zero score for unanswered questions. No LLM call made."""
    return GradeResponse(
        response_id=request.response_id,
        question_id=request.question_id,
        session_id=request.session_id,
        student_id=request.student_id,
        exam_id=request.exam_id,
        score=0.0,
        max_marks=request.max_marks,
        feedback=FeedbackDetail(strengths=[], weaknesses=["No answer provided"]),
        confidence=1.0,
        requires_review=False,
        graded_by="ai",
    )
