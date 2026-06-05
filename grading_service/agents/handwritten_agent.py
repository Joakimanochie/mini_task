"""
Handwritten Text Agent — uses Groq vision model to read
a student's handwritten canvas submission, extract the written content,
then evaluate it against the marking guide.
"""

import os
import json
from models.request import GradeRequest
from models.response import GradeResponse, FeedbackDetail
from utils.groq_client import get_groq_client
from utils.image_loader import load_image_as_base64

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.65"))
MODEL = os.getenv("GROQ_MODEL_VISION", "meta-llama/llama-4-scout-17b-16e-instruct")


async def grade_handwritten(request: GradeRequest) -> GradeResponse:
    client = get_groq_client()

    image_data, media_type = await load_image_as_base64(request.student_image_url)

    prompt = f"""You are an expert academic examiner reviewing a student's handwritten answer.

QUESTION:
{request.question}

MARKING GUIDE (expected answer with mark allocations):
{request.expected_answer}

MAXIMUM MARKS: {request.max_marks}

The image provided is the student's handwritten answer.
First, read and interpret the handwriting carefully.
If the handwriting is completely illegible, set confidence to 0.1 and flag for review.
Then grade the interpreted answer strictly against the marking guide.

Respond ONLY with a valid JSON object in exactly this format, no preamble, no markdown:
{{
  "score": <number between 0 and {request.max_marks}>,
  "confidence": <decimal between 0.0 and 1.0>,
  "strengths": [<what the student answered correctly per the marking guide>],
  "weaknesses": [<what was missing or incorrect per the marking guide>],
  "legibility_issue": <true if handwriting was difficult to read, false otherwise>
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
            "legibility_issue": True,
        }

    score = min(float(result.get("score", 0)), float(request.max_marks))
    confidence = float(result.get("confidence", 0.0))

    legibility_issue = result.get("legibility_issue", False)
    requires_review = confidence < CONFIDENCE_THRESHOLD or legibility_issue

    weaknesses = result.get("weaknesses", [])
    if legibility_issue:
        weaknesses.append("Note: Handwriting legibility issue detected — teacher review recommended")

    feedback = FeedbackDetail(
        strengths=result.get("strengths", []),
        weaknesses=weaknesses,
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
        requires_review=requires_review,
        graded_by="ai",
    )
