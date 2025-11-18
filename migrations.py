# migrate.py
from sqlmodel import Session, text
from db import engine

def migrate_database():
    """Add missing columns to existing tables"""
    with Session(engine) as session:
        try:
            # Add assignmentTimeLimit column if it doesn't exist
            session.execute(text("""
                ALTER TABLE assignment 
                ADD COLUMN assignmentTimeLimit INTEGER
            """))
            session.commit()
            print("✅ Added assignmentTimeLimit column to assignment table")
        except Exception as e:
            print(f"Column may already exist: {e}")
            session.rollback()

if __name__ == "__main__":
    migrate_database()