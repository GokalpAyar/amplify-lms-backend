import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

TEST_DB_PATH = Path(__file__).resolve().parent / "test_responses.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from db import engine  # noqa: E402
from main import app  # noqa: E402
from models import Assignment, Response, User  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database():
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_db_file():
    yield
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture
def client(reset_database):
    with TestClient(app) as test_client:
        yield test_client


def _seed_response(session: Session, rating: int = 4, comment: str = "Good but missed some words"):
    assignment = Assignment(
        title="Speaking Task",
        description="Practice prompt",
        questions={"q1": {"prompt": "Introduce yourself."}},
    )
    session.add(assignment)
    session.commit()
    session.refresh(assignment)

    response = Response(
        assignment_id=assignment.id,
        studentName="Jamie Student",
        jNumber="J123456",
        answers={"q1": "Answer text"},
        transcripts={"q1": "Transcript text"},
        student_accuracy_rating=rating,
        student_rating_comment=comment,
    )
    session.add(response)
    session.commit()
    session.refresh(response)

    return assignment, response


def _ensure_user(session: Session, user_id: str) -> None:
    """Create a minimal instructor record if it does not exist."""
    if session.get(User, user_id):
        return
    user = User(
        id=user_id,
        email=f"{user_id}@example.com",
        password_hash="demo-hash",
        role="instructor",
        name="Demo Instructor",
    )
    session.add(user)
    session.commit()


def test_list_responses_includes_student_rating_fields(client):
    with Session(engine) as session:
        _assignment, response = _seed_response(session)
        response_id = response.id
        student_name = response.studentName
        rating = response.student_accuracy_rating
        comment = response.student_rating_comment

    resp = client.get("/responses/")
    assert resp.status_code == 200

    data = resp.json()
    assert len(data) == 1

    record = data[0]
    assert record["id"] == response_id
    assert record["studentName"] == student_name
    assert record["student_accuracy_rating"] == rating
    assert record["student_rating_comment"] == comment


def test_assignment_response_listing_includes_student_ratings(client):
    with Session(engine) as session:
        assignment, response = _seed_response(session, rating=5, comment="Excellent transcript")
        assignment_id = assignment.id
        response_id = response.id

    resp = client.get(f"/responses/{assignment_id}")
    assert resp.status_code == 200

    data = resp.json()
    assert len(data) == 1

    record = data[0]
    assert record["id"] == response_id
    assert record["student_accuracy_rating"] == 5
    assert record["student_rating_comment"] == "Excellent transcript"


def test_demo_mode_assignment_creation_allows_owner_id_in_body(client):
    owner_id = "user_demo_owner"
    with Session(engine) as session:
        _ensure_user(session, owner_id)

    payload = {
        "title": "Demo Assignment",
        "description": "Created while DEMO_MODE true",
        "questions": {"q1": {"prompt": "Say hello."}},
        "owner_id": owner_id,
    }

    resp = client.post("/assignments/", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["owner_id"] == owner_id
    assert body["title"] == payload["title"]


def test_demo_mode_assignment_creation_requires_owner_id_when_no_token(client):
    payload = {
        "title": "Missing Owner",
        "description": "Should fail without owner_id in demo mode",
        "questions": {"q1": {"prompt": "Wave"}},
    }

    resp = client.post("/assignments/", json=payload)
    assert resp.status_code == 400
    assert "owner_id" in resp.json()["detail"]
