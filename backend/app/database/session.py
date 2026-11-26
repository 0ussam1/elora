from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# SQLite configuration requires connect_args check_same_thread=False
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema_migrations():
    """Safely add new columns to existing SQLite tables without data loss."""
    from sqlalchemy import text
    new_columns = [
        ("validation_status", "VARCHAR(32) DEFAULT 'UNCHECKED'"),
        ("canonical_url", "VARCHAR(1000)"),
        ("final_url", "VARCHAR(1000)"),
        ("http_status", "INTEGER"),
        ("validation_method", "VARCHAR(64)"),
        ("validation_reason", "TEXT"),
        ("validated_at", "DATETIME"),
        ("content_extraction_status", "VARCHAR(32) DEFAULT 'snippet_only'"),
        ("content_availability_status", "VARCHAR(32) DEFAULT 'unknown'"),
    ]
    with engine.connect() as conn:
        try:
            if settings.DATABASE_URL.startswith("sqlite"):
                rows = conn.execute(text("PRAGMA table_info(research_results)")).fetchall()
                if not rows:
                    return
                existing = {row[1] for row in rows}
                for col_name, col_type in new_columns:
                    if col_name not in existing:
                        conn.execute(text(f"ALTER TABLE research_results ADD COLUMN {col_name} {col_type}"))
                conn.commit()
        except Exception:
            pass
