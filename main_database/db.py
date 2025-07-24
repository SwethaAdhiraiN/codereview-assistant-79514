import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# Database configuration (ENV VARS: DB_URL)
DATABASE_URL = os.environ.get("MAIN_DATABASE_URL") or os.environ.get("DB_URL")
if not DATABASE_URL:
    raise RuntimeError("MAIN_DATABASE_URL or DB_URL environment variable must be set.")

engine = create_engine(DATABASE_URL, future=True, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# PUBLIC_INTERFACE
def get_db():
    """Yield a SQLAlchemy session (for FastAPI dependency)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
