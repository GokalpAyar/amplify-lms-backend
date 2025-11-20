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
        
        for column, column_type in (
            ("audio_storage_path", "TEXT"),
            ("audio_file_url", "TEXT"),
            ("audio_file_size", "BIGINT"),
            ("audio_mime_type", "TEXT"),
        ):
            try:
                session.execute(
                    text(f"""
                        ALTER TABLE response
                        ADD COLUMN {column} {column_type}
                    """)
                )
                print(f"✅ Added {column} column to response table")
            except Exception as e:
                print(f"{column} column may already exist: {e}")
        
        session.commit()

if __name__ == "__main__":
    migrate_database()