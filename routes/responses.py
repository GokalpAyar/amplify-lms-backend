# routes/responses.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from db import get_session
from models import Response, Assignment, User
from schemas import ResponseCreate, ResponseOut
from routes.assignments import get_current_user

router = APIRouter(prefix="/responses", tags=["responses"])

# 🆕 ADD THIS POST ENDPOINT FOR STUDENT SUBMISSIONS
@router.post("/", response_model=ResponseOut)
def create_response(
    payload: ResponseCreate,
    session: Session = Depends(get_session)
):
    """Create a new student response (no authentication required for students)"""
    
    print(f"🎯 Received student submission: {payload.studentName} for assignment {payload.assignment_id}")
    
    # Check if assignment exists
    assignment = session.get(Assignment, payload.assignment_id)
    if not assignment:
        print(f"❌ Assignment not found: {payload.assignment_id}")
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    print(f"✅ Assignment found: {assignment.title}")
    
    # Optional: Check for duplicate submission (same student + same assignment)
    existing = session.exec(
        select(Response).where(
            Response.assignment_id == payload.assignment_id,
            Response.jNumber == payload.jNumber
        )
    ).first()
    
    if existing:
        print(f"⚠️ Duplicate submission detected: {payload.jNumber}")
        raise HTTPException(
            status_code=400, 
            detail="You have already submitted this assignment"
        )
    
    # Create and save the response
    response = Response(**payload.dict())
    session.add(response)
    session.commit()
    session.refresh(response)
    
    print(f"✅ Student submission saved: {payload.studentName} ({payload.jNumber})")
    print(f"   - Answers: {len(payload.answers)} questions")
    print(f"   - Transcripts: {len(payload.transcripts)} oral responses")
    
    return response

# Your existing GET endpoints remain the same...
@router.get("/")
def list_responses(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get only responses to the current instructor's assignments"""
    
    # Get all assignments owned by this instructor
    instructor_assignments = session.exec(
        select(Assignment).where(Assignment.owner_id == current_user.id)
    ).all()
    
    assignment_ids = [assignment.id for assignment in instructor_assignments]
    
    if not assignment_ids:
        return []
    
    # Get responses only for these assignments
    responses = session.exec(
        select(Response).where(Response.assignment_id.in_(assignment_ids))
    ).all()
    
    return responses

@router.get("/{assignment_id}")
def get_responses_for_assignment(
    assignment_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get responses for a specific assignment, but only if owned by current instructor"""
    
    # Verify the assignment belongs to this instructor
    assignment = session.get(Assignment, assignment_id)
    if not assignment or assignment.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Get responses for this assignment
    responses = session.exec(
        select(Response).where(Response.assignment_id == assignment_id)
    ).all()
    
    return responses