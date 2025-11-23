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


def _seed_user(session: Session, email: str, user_id: str) -> User:
    user = User(id=user_id, email=email, password_hash="hashed", role="instructor")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_assignment_listing_scoped_to_authenticated_user(client):
    with Session(engine) as session:
        owner_a = _seed_user(session, "teacher-a@example.com", "user_a")
        owner_b = _seed_user(session, "teacher-b@example.com", "user_b")

        assignment_a = Assignment(
            title="Owner A Assignment",
            description="Only owner A should see this.",
            questions={"q1": {"prompt": "Question A"}},
            owner_id=owner_a.id,
        )
        assignment_b = Assignment(
            title="Owner B Assignment",
            description="Only owner B should see this.",
            questions={"q1": {"prompt": "Question B"}},
            owner_id=owner_b.id,
        )
        session.add(assignment_a)
        session.add(assignment_b)
        session.commit()

        owner_a_id = owner_a.id
        owner_b_id = owner_b.id

    resp_a = client.get("/assignments/", headers={"X-User-Id": owner_a_id})
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert len(data_a) == 1
    assert data_a[0]["title"] == "Owner A Assignment"

    resp_b = client.get("/assignments/", headers={"X-User-Id": owner_b_id})
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert len(data_b) == 1
    assert data_b[0]["title"] == "Owner B Assignment"


def test_assignment_creation_uses_authenticated_owner_id(client):
    with Session(engine) as session:
        owner = _seed_user(session, "creator@example.com", "teacher_123")
        owner_id = owner.id

    payload = {
        "title": "New Unit",
        "description": "Created via API",
        "questions": {"q1": {"prompt": "Describe something."}},
        "owner_id": "someone_else",
    }

    resp = client.post("/assignments/", json=payload, headers={"X-User-Id": owner_id})
    assert resp.status_code == 200

    data = resp.json()
    assert data["owner_id"] == owner_id
    assignment_id = data["id"]

    with Session(engine) as session:
        assignment = session.get(Assignment, assignment_id)
        assert assignment is not None
        assert assignment.owner_id == owner_id
