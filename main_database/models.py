from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Text,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from .db import Base

# PUBLIC_INTERFACE
class User(Base):
    """User model for registered accounts."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(128), unique=True, index=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    sessions = relationship("Session", back_populates="user")
    uploads = relationship("RepositoryUpload", back_populates="user")

# PUBLIC_INTERFACE
class Session(Base):
    """Session tokens for user login/auth."""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(64), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="sessions")

# PUBLIC_INTERFACE
class RepositoryUpload(Base):
    """Model for recording each uploaded / analyzed repository event."""
    __tablename__ = "repository_uploads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    repo_path = Column(Text, nullable=False)
    upload_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    analysis_results = relationship("AnalysisResult", back_populates="upload")
    user = relationship("User", back_populates="uploads")

# PUBLIC_INTERFACE
class AnalysisResult(Base):
    """
    Stores results of code review/LLM generation for a given RepositoryUpload event.
    """
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(Integer, ForeignKey("repository_uploads.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    commit_message = Column(Text)
    code_suggestions = Column(JSON)
    detected_issues = Column(JSON)
    raw_llm_response = Column(JSON)
    upload = relationship("RepositoryUpload", back_populates="analysis_results")
