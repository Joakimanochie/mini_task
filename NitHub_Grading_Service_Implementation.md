# NitHub AI Grading Service — Implementation Guide

> **For:** Claude Code  
> **Stack:** Python, FastAPI, Groq SDK  
> **Role:** AI Grading Microservice (called by Node.js backend)  
> **Last Updated:** June 2026

---

## 1. Context & Purpose

This service is the AI grading engine for the NitHub Automated Examination Management System. The Node.js backend calls this FastAPI service after a student submits an exam. The service grades each question individually and returns structured results that Node.js writes to the PostgreSQL database.

**This service does NOT connect to the database directly.** It only receives data, grades it, and returns results. Node.js owns all DB writes.

---

## 2. Database Schema Reference

The following tables are relevant. This service never writes to them — Node.js does — but you need to understand the shape of data being passed in.

### `questions`
| Field | Type | Notes |
|---|---|---|
| id | string PK | question_id passed in every request |
| question_type | string | `"mcq"` \| `"theory"` \| `"handwritten"` \| `"diagram"` |
| response_type | string | `"text"` \| `"handwritten"` \| `"diagram"` |
| content | text | The question text |
| expected_answer | text | **This is the marking guide** — teacher-written rubric with mark allocations |
| marks | int | Maximum marks for this question |

### `responses`
| Field | Type | Notes |
|---|---|---|
| id | string PK | response_id passed in every request |
| session_id | string FK | Links to exam_sessions |
| question_id | string FK | Links to questions |
| text_response | text | Student's typed/theory answer |
| image_url | string | URL to canvas drawing (handwritten or diagram) |
| selected_option_id | string FK | MCQ only — which option the student picked |

### `grades` (Node.js writes this after FastAPI responds)
| Field | Type | Notes |
|---|---|---|
| id | string PK | |
| response_id | string FK | |
| ai_score | decimal | Score returned by this service |
| manual_score | decimal | NULL initially, set if teacher overrides |
| final_score | decimal | Same as ai_score initially |
| feedback | JSONB | `{ "strengths": [], "weaknesses": [] }` |
| confidence | decimal | **NEW field** — AI certainty 0.00–1.00 |
| requires_review | boolean | **NEW field** — true if confidence below threshold |
| graded_by | string | Always `"ai"` from this service |
| graded_at | timestamp | Set by Node.js |

### Required SQL Migrations (run these before deploying)
```sql
ALTER TABLE grades
  ADD COLUMN confidence      DECIMAL(4,3),
  ADD COLUMN requires_review BOOLEAN DEFAULT false;

ALTER TABLE grades
  ALTER COLUMN feedback TYPE JSONB
  USING feedback::JSONB;
```

---

## 3. Project Structure

Create the following file structure:

```
grading_service/
├── main.py                  # FastAPI app entry point
├── router.py                # POST /grade endpoint + agent routing logic
├── agents/
│   ├── __init__.py
│   ├── mcq_agent.py         # Deterministic MCQ grader
│   ├── theory_agent.py      # Groq LLM text grader
│   ├── handwritten_agent.py # Groq vision — handwritten text
│   └── diagram_agent.py     # Groq vision — diagram comparison
├── models/
│   ├── __init__.py
│   ├── request.py           # Pydantic request model
│   └── response.py          # Pydantic response model
├── utils/
│   ├── __init__.py
│   ├── image_loader.py      # Fetches image from URL → base64
│   └── groq_client.py       # Shared Groq client singleton
├── .env                     # GROQ_API_KEY, CONFIDENCE_THRESHOLD
├── requirements.txt
└── README.md
```

---

## 4. Dependencies

### `requirements.txt`
```
fastapi==0.111.0
uvicorn==0.29.0
groq==0.9.0
pydantic==2.7.1
python-dotenv==1.0.1
httpx==0.27.0
```

---

## 5. Environment Variables

### `.env`
```env
GROQ_API_KEY=your_groq_api_key_here
CONFIDENCE_THRESHOLD=0.65
GROQ_MODEL_TEXT=meta-llama/llama-4-scout-17b-16e-instruct
GROQ_MODEL_VISION=meta-llama/llama-4-scout-17b-16e-instruct
```

> **Note:** Both text and vision use the same Llama 4 Scout model on Groq. This is the same model used in the prototype.

---

## 6. Pydantic Models

### `models/request.py`
```python
from pydantic import BaseModel
from typing import Optional, Literal

class GradeRequest(BaseModel):
    # Identifiers — used for tracing, not DB writes
    session_id: str
    student_id: str
    exam_id: str
    response_id: str
    question_id: str

    # Question metadata
    question_type: Literal["mcq", "theory", "handwritten", "diagram"]
    response_type: str
    question: str
    expected_answer: str        # This is the marking guide
    max_marks: int

    # Student answer — one of these will be populated
    student_text: Optional[str] = None       # theory answers
    student_image_url: Optional[str] = None  # handwritten or diagram
    selected_option_id: Optional[str] = None # MCQ
    correct_option_id: Optional[str] = None  # MCQ — Node.js resolves this before calling
```

### `models/response.py`
```python
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
    confidence: float           # 0.00 – 1.00
    requires_review: bool       # true if confidence < CONFIDENCE_THRESHOLD
    graded_by: str              # always "ai"
```

---

## 7. Shared Utilities

### `utils/groq_client.py`
```python
import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_groq_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client
```

### `utils/image_loader.py`
```python
import httpx
import base64
from typing import Tuple

async def load_image_as_base64(image_url: str) -> Tuple[str, str]:
    """
    Fetches image from a URL and returns (base64_string, media_type).
    Used by handwritten and diagram agents.
    The URL comes from responses.image_url (stored by Node.js after canvas upload).
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(image_url, timeout=15.0)
        response.raise_for_status()

    content_type = response.headers.get("content-type", "image/png")
    media_type = content_type.split(";")[0].strip()

    base64_data = base64.b64encode(response.content).decode("utf-8")
    return base64_data, media_type
```

---

## 8. Agents

### `agents/mcq_agent.py`
```python
"""
MCQ Agent — fully deterministic, no LLM call.
Node.js resolves the correct_option_id before calling this service.
We simply compare selected_option_id against correct_option_id.
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
        confidence=1.0,         # deterministic — always 100% confident
        requires_review=False,
        graded_by="ai",
    )
```

### `agents/theory_agent.py`
```python
"""
Theory Agent — uses Groq LLM to evaluate student text answer
against the teacher's expected_answer (marking guide).
Returns score, structured feedback, and confidence level.
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
        # Fallback if model returns non-JSON
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
```

### `agents/handwritten_agent.py`
```python
"""
Handwritten Text Agent — uses Groq vision model to read
a student's handwritten canvas submission (image URL from responses.image_url),
extract the written content, then evaluate it against the marking guide.
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

    # Force review if legibility was flagged
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
```

### `agents/diagram_agent.py`
```python
"""
Diagram Agent — uses Groq vision model to evaluate a student's
drawn diagram (canvas image) against the teacher's marking guide.
This is the upgraded version of the mini_task prototype.
No reference image is required — grading is purely against
the text marking guide describing expected elements and labels.
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
```

---

## 9. Router

### `router.py`
```python
"""
Main grading endpoint.
Receives a grading request from Node.js,
routes to the correct agent based on question_type,
returns a structured GradeResponse.
"""

from fastapi import APIRouter, HTTPException
from models.request import GradeRequest
from models.response import GradeResponse
from agents.mcq_agent import grade_mcq
from agents.theory_agent import grade_theory
from agents.handwritten_agent import grade_handwritten
from agents.diagram_agent import grade_diagram

router = APIRouter()


@router.post("/grade", response_model=GradeResponse)
async def grade(request: GradeRequest) -> GradeResponse:
    """
    Grading endpoint called by Node.js backend.
    
    Grading order per Node.js call pattern:
      exam_id → student_id → question_id (one call per question, sequential)
    
    Node.js calls this once per question_id, in order, 
    until all responses under a session are graded.
    """

    question_type = request.question_type

    try:
        if question_type == "mcq":
            return grade_mcq(request)

        elif question_type == "theory":
            if not request.student_text:
                # Empty answer — return zero, no LLM call needed
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

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Grading failed for question {request.question_id}: {str(e)}"
        )


def _empty_response(request: GradeRequest) -> GradeResponse:
    """Returns a zero score for unanswered questions. No LLM call made."""
    from models.response import FeedbackDetail
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
```

---

## 10. Entry Point

### `main.py`
```python
from fastapi import FastAPI
from router import router

app = FastAPI(
    title="NitHub AI Grading Service",
    description="AI grading microservice for the NitHub examination platform",
    version="1.0.0",
)

app.include_router(router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "nithub-grading-service"}
```

---

## 11. Node.js Integration Contract

This is exactly what the Node.js backend must send and can expect back.

### Request Node.js sends to `POST /grade`

```json
{
  "session_id": "sess_abc123",
  "student_id": "stu_xyz456",
  "exam_id": "exam_def789",
  "response_id": "resp_111",
  "question_id": "ques_222",
  "question_type": "theory",
  "response_type": "text",
  "question": "Explain the process of photosynthesis.",
  "expected_answer": "Award 3 marks for: light energy absorbed by chlorophyll (1), water split to release oxygen (1), glucose produced from CO2 (1).",
  "max_marks": 3,
  "student_text": "Photosynthesis is when plants use sunlight to make food from carbon dioxide and water.",
  "student_image_url": null,
  "selected_option_id": null,
  "correct_option_id": null
}
```

### Response FastAPI returns

```json
{
  "response_id": "resp_111",
  "question_id": "ques_222",
  "session_id": "sess_abc123",
  "student_id": "stu_xyz456",
  "exam_id": "exam_def789",
  "score": 2.0,
  "max_marks": 3,
  "feedback": {
    "strengths": [
      "Correctly identified sunlight as energy source",
      "Correctly mentioned CO2 and water as inputs"
    ],
    "weaknesses": [
      "Did not mention chlorophyll absorbing light energy specifically",
    ]
  },
  "confidence": 0.82,
  "requires_review": false,
  "graded_by": "ai"
}
```

### Node.js DB Write After Receiving Response

```javascript
// After receiving GradeResponse from FastAPI:
await db.query(`
  INSERT INTO grades (
    response_id, ai_score, final_score,
    feedback, confidence, requires_review,
    graded_by, graded_at
  ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
`, [
  gradeResponse.response_id,
  gradeResponse.score,
  gradeResponse.score,                        // final_score = ai_score initially
  JSON.stringify(gradeResponse.feedback),     // JSONB
  gradeResponse.confidence,
  gradeResponse.requires_review,
  "ai"
]);

// After ALL questions graded for this session:
await db.query(`
  INSERT INTO exam_results (
    session_id, total_score, max_score,
    pass_status, published, published_at
  ) VALUES ($1, $2, $3, $4, false, null)
`, [
  session_id,
  totalScore,   // SUM of all grades.final_score for this session
  maxScore,     // SUM of all questions.marks for this exam
  false         // teacher sets pass_status manually when publishing
]);

// Notify student:
await db.query(`
  INSERT INTO notifications (user_id, type, title, message, read, created_at)
  VALUES ($1, 'exam_graded', 'Your exam has been graded',
          'Your results are ready for review.', false, NOW())
`, [student_user_id]);
```

---

## 12. Running the Service

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn main:app --reload --port 8000

# Production (on Ubuntu with PM2)
pm2 start "uvicorn main:app --host 0.0.0.0 --port 8000" --name nithub-grading
```

### API will be available at:
- `POST http://localhost:8000/grade` — main grading endpoint
- `GET  http://localhost:8000/health` — health check for Node.js to ping
- `GET  http://localhost:8000/docs` — auto-generated Swagger UI

---

## 13. Key Implementation Rules

1. **Never connect to the database** — this service is stateless. All DB reads/writes are Node.js's responsibility.

2. **Always return a valid `GradeResponse`** — never let an exception propagate to Node.js without a proper HTTP error response.

3. **MCQ never calls Groq** — it is deterministic. Node.js must resolve `correct_option_id` from `mcq_options.is_correct` before calling this service.

4. **Empty answers never call Groq** — the `_empty_response` helper handles these instantly with zero score.

5. **`temperature=0.1` on all LLM calls** — keeps grading consistent and deterministic across students.

6. **`confidence < CONFIDENCE_THRESHOLD` triggers `requires_review=true`** — threshold is set in `.env` (default 0.65). Teacher sees these flagged in their dashboard.

7. **`feedback` must always be JSONB-serializable** — Node.js casts it directly into the `grades.feedback` JSONB column.

8. **Image loading is async** — `grade_handwritten` and `grade_diagram` are `async` functions. The router `await`s them. `grade_mcq` and `grade_theory` are synchronous.
