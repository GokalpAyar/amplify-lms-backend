# complete_migration.py
from sqlmodel import Session, text
from db import engine

def migrate_database():
    """Add all missing columns to existing tables"""
    with Session(engine) as session:
        try:
            # Add owner_id column if it doesn't exist
            session.execute(text("""
                ALTER TABLE assignment 
                ADD COLUMN owner_id TEXT
            """))
            print("✅ Added owner_id column to assignment table")
        except Exception as e:
            print(f"owner_id column may already exist: {e}")
        
        try:
            # Add assignmentTimeLimit column if it doesn't exist
            session.execute(text("""
                ALTER TABLE assignment 
                ADD COLUMN assignmentTimeLimit INTEGER
            """))
            print("✅ Added assignmentTimeLimit column to assignment table")
        except Exception as e:
            print(f"assignmentTimeLimit column may already exist: {e}")

        try:
            session.execute(text("""
                ALTER TABLE response
                ADD COLUMN student_accuracy_rating INTEGER
            """))
            print("✅ Added student_accuracy_rating column to response table")
        except Exception as e:
            print(f"student_accuracy_rating column may already exist: {e}")

        try:
            session.execute(text("""
                ALTER TABLE response
                ADD COLUMN student_rating_comment TEXT
            """))
            print("✅ Added student_rating_comment column to response table")
        except Exception as e:
            print(f"student_rating_comment column may already exist: {e}")

        try:
            session.execute(text("""
                ALTER TABLE response
                ADD COLUMN owner_id TEXT
            """))
            print("✅ Added owner_id column to response table")
        except Exception as e:
            print(f"owner_id column on response may already exist: {e}")

        try:
            session.execute(text("""
                UPDATE response
                SET owner_id = assignment.owner_id
                FROM assignment
                WHERE response.assignment_id = assignment.id
                  AND assignment.owner_id IS NOT NULL
                  AND (response.owner_id IS NULL OR response.owner_id = '')
            """))
            print("✅ Backfilled response.owner_id using related assignments")
        except Exception as e:
            print(f"Unable to backfill response.owner_id: {e}")
        
        session.commit()

if __name__ == "__main__":
    migrate_database()