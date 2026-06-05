"""
Diagram Agent — uses Groq vision model to evaluate a student's
drawn diagram (canvas image) against the teacher's marking guide.
No reference image required — grading is purely against the text
marking guide describing expected elements and labels.
"""

import os
import json
from models.request import GradeRequest
from models.response import GradeResponse, FeedbackDetail
from utils.groq_client import get_groq_client
from utils.image_loader import load_image_as_base64

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.65"))
MODEL = os.getenv("GROQ_MODEL_VISION", "meta-llama/llama-4-scout-17b-16e-instruct")


async def grade_diagram(request: GradeRequest) -> GradeResponse:
    client = get_groq_client()

    image_data, media_type = await load_image_as_base64(request.student_image_url)

    prompt = f"""You are an expert academic examiner reviewing a student's hand-drawn diagram.

QUESTION:
{request.question}

MARKING GUIDE (required elements, labels, and mark allocations):
{request.expected_answer}

MAXIMUM MARKS: {request.max_marks}

The image provided is the student's drawn diagram submitted on a digital canvas.
Carefully examine the diagram and evaluate it strictly against the marking guide.
Check for: required elements, correct labels, accurate structure, and completeness.

Respond ONLY with a valid JSON object in exactly this format, no preamble, no markdown:
{{
  "score": <number between 0 and {request.max_marks}>,
  "confidence": <decimal between 0.0 and 1.0>,
  "strengths": [<elements/labels present and correctly drawn per the marking guide>],
  "weaknesses": [<elements/labels missing or incorrectly drawn per the marking guide>]
}}"""

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{image_data}"
                    }
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        }],
        temperature=0.1,
    )

    raw = completion.choices[0].message.content.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "score": 0,
            "confidence": 0.0,
            "strengths": [],
            "weaknesses": ["Grading failed — manual review required"],
        }

    score = min(float(result.get("score", 0)), float(request.max_marks))
    confidence = float(result.get("confidence", 0.0))

    feedback = FeedbackDetail(
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
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
        confidence=confidence,
        requires_review=confidence < CONFIDENCE_THRESHOLD,
        graded_by="ai",
    )
