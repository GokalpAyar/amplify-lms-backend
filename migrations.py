# migrate.py
from sqlalchemy import inspect
from sqlmodel import Session, text

from db import engine


def _ensure_column(session: Session, table: str, column: str, column_type: str) -> None:
    inspector = inspect(session.bind)
    existing_columns = {col["name"] for col in inspector.get_columns(table)}

    if column in existing_columns:
        print(f"ℹ️  {table}.{column} already exists; skipping.")
        return

    session.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {column} {column_type}'))
    print(f"✅ Added {table}.{column} column ({column_type}).")


def _add_assignment_time_limit(session: Session) -> None:
    _ensure_column(session, "assignment", "assignmentTimeLimit", "INTEGER")


def _add_response_audio_columns(session: Session) -> None:
    column_defs = [
        ("audio_file_url", "TEXT"),
        ("audio_storage_path", "TEXT"),
        ("audio_mime_type", "TEXT"),
        ("audio_file_size", "BIGINT"),
    ]

    for column, column_type in column_defs:
        _ensure_column(session, "response", column, column_type)


def migrate_database() -> None:
    """Add any missing columns required by the latest Response model."""
    with Session(engine) as session:
        try:
            _add_assignment_time_limit(session)
            _add_response_audio_columns(session)
            session.commit()
        except Exception as exc:
            session.rollback()
            print(f"⚠️ Migration failed: {exc}")
            raise


if __name__ == "__main__":
    migrate_database()