"""
Theory Agent — uses Groq LLM to evaluate student text answer
against the teacher's expected_answer (marking guide).
"""

import os
import json
from models.request import GradeRequest
from models.response import GradeResponse, FeedbackDetail
from utils.groq_client import get_groq_client

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.65"))
MODEL = os.getenv("GROQ_MODEL_TEXT", "meta-llama/llama-4-scout-17b-16e-instruct")


def grade_theory(request: GradeRequest) -> GradeResponse:
    client = get_groq_client()

    prompt = f"""You are an expert academic examiner. Your task is to grade a student's answer strictly according to the marking guide provided by the teacher.

QUESTION:
{request.question}

MARKING GUIDE (expected answer with mark allocations):
{request.expected_answer}

MAXIMUM MARKS: {request.max_marks}

STUDENT ANSWER:
{request.student_text or "[No answer provided]"}

Grade the student's answer based ONLY on the marking guide. Do not award marks for correct information that is not in the marking guide.

Respond ONLY with a valid JSON object in exactly this format, no preamble, no markdown:
{{
  "score": <number between 0 and {request.max_marks}>,
  "confidence": <decimal between 0.0 and 1.0 representing your certainty in this grade>,
  "strengths": [<list of strings — what the student answered correctly per the marking guide>],
  "weaknesses": [<list of strings — what was missing or incorrect per the marking guide>]
}}"""

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
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
