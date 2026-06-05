from pydantic import BaseModel
from typing import Optional, Literal


class GradeRequest(BaseModel):
    session_id: str
    student_id: str
    exam_id: str
    response_id: str
    question_id: str

    question_type: Literal["mcq", "theory", "handwritten", "diagram"]
    response_type: str
    question: str
    expected_answer: str
    max_marks: int

    student_text: Optional[str] = None
    student_image_url: Optional[str] = None
    selected_option_id: Optional[str] = None
    correct_option_id: Optional[str] = None
