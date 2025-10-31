from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any
from uuid import uuid4
import io

try:
    import docx  # for parsing Word files
    HAS_DOCX = True
except Exception:
    HAS_DOCX = False

app = FastAPI(title="LMS API Bridge", version="0.1")

# Allow frontend running on localhost:5173 (Vite/React)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ASSIGNMENTS: Dict[str, Dict[str, Any]] = {}

class Submission(BaseModel):
    assignmentId: str
    studentId: str
    responses: Dict[str, Any]

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/upload-assignment/")
async def upload_assignment(file: UploadFile = File(...)):
    contents = await file.read()
    lines = []

    if HAS_DOCX and file.filename.lower().endswith(".docx"):
        doc = docx.Document(io.BytesIO(contents))
        for p in doc.paragraphs:
            t = p.text.strip()
            if t:
                lines.append(t)
    else:
        try:
            text = contents.decode("utf-8", errors="ignore")
            lines = [l.strip() for l in text.splitlines() if l.strip()]
        except Exception:
            lines = []

    assignment_id = str(uuid4())
    questions = []
    for i, line in enumerate(lines, start=1):
        qid = f"q{i}"
        if line.endswith("?"):
            questions.append({
                "id": qid,
                "type": "mcq",
                "stem": line,
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "answer": None
            })
        else:
            questions.append({
                "id": qid,
                "type": "open",
                "prompt": line
            })

    ASSIGNMENTS[assignment_id] = {
        "assignmentId": assignment_id,
        "title": file.filename,
        "questions": questions
    }

    return {
        "assignmentId": assignment_id,
        "shareLink": f"/student/{assignment_id}",
        "questionsCount": len(questions)
    }

@app.get("/assignments/{assignment_id}")
def get_assignment(assignment_id: str):
    return ASSIGNMENTS.get(assignment_id, {"error": "Not found"})

@app.post("/submissions/")
def grade_submission(payload: Submission):
    assignment = ASSIGNMENTS.get(payload.assignmentId)
    if not assignment:
        return {"error": "Assignment not found"}

    total = len(assignment["questions"])
    answered = sum(1 for q in assignment["questions"] if payload.responses.get(q["id"]))
    score = round((answered / max(total, 1)) * 100, 1)

    return {
        "score": score,
        "answered": answered,
        "total": total,
        "feedback": "Thanks for your submission! (Demo grader)"
    }
