import os
import shutil
from typing import List, Optional

from fastapi import (
    FastAPI,
    File,
    UploadFile,
    Form,
    HTTPException,
    Depends,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import hashlib
import secrets
import subprocess
import tempfile

# === DB connection setup ===
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../main_database")))
import db as db_module
import models as models_module

from sqlalchemy.orm import Session

# === App Setup ===

app = FastAPI(
    title="CodeReview Assistant Backend",
    description="Backend for Git code review and productivity enhancement with LLM support.",
    version="1.0.0",
    openapi_tags=[
        {"name": "auth", "description": "User login/session handling"},
        {"name": "repo", "description": "Git repo upload and analysis"},
        {"name": "analysis", "description": "Analysis and history retrieval"}
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # update as needed for security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# === Utility functions for authentication, hashing, etc. ===

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

def get_token() -> str:
    return secrets.token_hex(32)

def get_db():
    yield from db_module.get_db()

# === Pydantic Schemas ===

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, description="Username")
    email: str = Field(..., description="Email")
    password: str = Field(..., min_length=6, description="Password")

class UserRead(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime

class SessionRead(BaseModel):
    token: str
    user_id: int
    created_at: datetime
    expires_at: Optional[datetime]

class RepoUploadInput(BaseModel):
    repo_path: str = Field(..., description="Path to the uploaded repository (on server-side)")

class AnalysisResultRead(BaseModel):
    id: int
    upload_id: int
    created_at: datetime
    commit_message: Optional[str]
    code_suggestions: Optional[dict]
    detected_issues: Optional[dict]
    raw_llm_response: Optional[dict]

class GenericResponse(BaseModel):
    detail: str

# === AUTH ENDPOINTS ===

# PUBLIC_INTERFACE
@app.post("/register", response_model=UserRead, tags=["auth"], summary="Register a new user", responses={400: {"model": GenericResponse}})
def register(user: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user.
    """
    existing = db.query(models_module.User).filter(
        (models_module.User.username == user.username) | (models_module.User.email == user.email)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already exists")
    new_user = models_module.User(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return UserRead(
        id=new_user.id,
        username=new_user.username,
        email=new_user.email,
        created_at=new_user.created_at,
    )

# PUBLIC_INTERFACE
@app.post("/login", response_model=SessionRead, tags=["auth"], summary="Log in a user (returns session token)")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Log in and get a session token.
    """
    user = db.query(models_module.User).filter(models_module.User.username == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = get_token()
    session_obj = models_module.Session(
        user_id=user.id,
        token=token,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    db.add(session_obj)
    db.commit()
    db.refresh(session_obj)
    return SessionRead(
        token=session_obj.token,
        user_id=user.id,
        created_at=session_obj.created_at,
        expires_at=session_obj.expires_at
    )

def get_user_by_token(token: str, db: Session):
    return db.query(models_module.Session).filter(models_module.Session.token == token).first()

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    session_obj = db.query(models_module.Session).filter(models_module.Session.token == token).first()
    if not session_obj or session_obj.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Invalid/expired token")
    user = db.query(models_module.User).filter(models_module.User.id == session_obj.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# === REPO UPLOAD AND ANALYSIS LOGIC ===

# Helper: save uploaded file to temp and return path.
def save_upload_file_tmp(upload_file: UploadFile) -> str:
    suffix = os.path.splitext(upload_file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(upload_file.file, tmp)
        return tmp.name

# PUBLIC_INTERFACE
@app.post("/repo/upload", tags=["repo"], summary="Upload a Git repo (as a zipped archive)", responses={200: {"model": GenericResponse}})
async def upload_repo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models_module.User = Depends(get_current_user),
):
    """
    Upload a zipped Git repository for analysis.
    """
    if not file.filename.endswith(".zip"):
        return JSONResponse(status_code=400, content={"detail": "Only .zip files are accepted"})
    tmp_path = save_upload_file_tmp(file)
    # Extract to a working directory
    repo_dir = tempfile.mkdtemp(prefix="repo_upload_")
    try:
        shutil.unpack_archive(tmp_path, repo_dir)
    except Exception as e:
        cleanup(tmp_path, repo_dir)
        return JSONResponse(status_code=400, content={"detail": "Unzip failed: {}".format(str(e))})

    # Register repo upload record in DB
    repo_upload = models_module.RepositoryUpload(
        user_id=current_user.id,
        repo_path=repo_dir,
        upload_time=datetime.utcnow()
    )
    db.add(repo_upload)
    db.commit()
    db.refresh(repo_upload)
    # Optional: Remove zip but keep extracted dir for analysis
    if os.path.isfile(tmp_path):
        os.remove(tmp_path)
    return {"detail": "Repository uploaded and extracted for analysis", "upload_id": repo_upload.id}

def cleanup(*paths):
    for p in paths:
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        elif os.path.isfile(p):
            os.remove(p)

# PUBLIC_INTERFACE
@app.post("/repo/analyze", tags=["analysis"], summary="Run code analysis on uploaded repo", responses={200: {"model": AnalysisResultRead}})
def analyze_repo(
    upload_id: int = Form(..., description="Upload ID returned from /repo/upload"),
    db: Session = Depends(get_db),
    current_user: models_module.User = Depends(get_current_user),
):
    """
    Runs code analysis on uploaded repo (git diff, ripgrep, LLM assist).
    """
    repo: models_module.RepositoryUpload = db.query(models_module.RepositoryUpload).filter(
        models_module.RepositoryUpload.id == upload_id
    ).first()
    if not repo or repo.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Upload not found or not owned by user")
    repo_path = repo.repo_path
    # === Run git diff ===
    git_out = try_git_diff(repo_path)
    # === Run ripgrep ===
    rg_out = try_ripgrep(repo_path)
    # === Call LLM/CrewAI for commit message/optimization (placeholder) ===
    commit_message, suggestions, issues, raw_llm = call_llm_tools(git_out, rg_out, repo_path)

    # Save result in DB
    res_obj = models_module.AnalysisResult(
        upload_id=repo.id,
        commit_message=commit_message,
        code_suggestions=suggestions,
        detected_issues=issues,
        raw_llm_response=raw_llm,
        created_at=datetime.utcnow(),
    )
    db.add(res_obj)
    db.commit()
    db.refresh(res_obj)
    return AnalysisResultRead(
        id=res_obj.id,
        upload_id=repo.id,
        created_at=res_obj.created_at,
        commit_message=commit_message,
        code_suggestions=suggestions,
        detected_issues=issues,
        raw_llm_response=raw_llm,
    )

def try_git_diff(path: str) -> str:
    # If .git exists, get diff; else, try to init and diff all
    git_dir = os.path.join(path, ".git")
    if not os.path.isdir(git_dir):
        subprocess.run(["git", "init"], cwd=path)
    try:
        out = subprocess.check_output(["git", "status", "--porcelain"], cwd=path)
        has_changes = bool(out.strip())
        if not has_changes:
            return ""
        diff = subprocess.check_output(["git", "diff"], cwd=path)
        return diff.decode("utf-8", errors="ignore")
    except Exception:
        return ""
    
def try_ripgrep(path: str) -> str:
    try:
        rg = subprocess.check_output(["rg", "--json", "."], cwd=path)
        return rg.decode("utf-8", errors="ignore")
    except Exception:
        return ""
    
def call_llm_tools(git_diff: str, rg_results: str, repo_path: str):
    """
    Placeholder for LLM/CrewAI. Returns fake output in this implementation.
    """
    # In a true implementation, connect to LLM via API or local inference here.
    fake_commit_message = "chore: update code after review"
    fake_suggestions = {"refactor": "Refactoring opportunities found in foo.py"}
    fake_issues = {"warnings": ["Potential unused variable found in bar.py"]}
    fake_raw = {"llm_input": git_diff, "llm_output": fake_commit_message}
    return fake_commit_message, fake_suggestions, fake_issues, fake_raw

# PUBLIC_INTERFACE
@app.get("/analysis/{upload_id}", tags=["analysis"], response_model=List[AnalysisResultRead], summary="Get results of previous analyses on a repo")
def get_analysis(upload_id: int, db: Session = Depends(get_db), current_user: models_module.User = Depends(get_current_user)):
    """
    Fetch all analysis results for an upload.
    """
    res_q = db.query(models_module.AnalysisResult).filter(models_module.AnalysisResult.upload_id == upload_id).all()
    return [AnalysisResultRead(
        id=r.id,
        upload_id=r.upload_id,
        created_at=r.created_at,
        commit_message=r.commit_message,
        code_suggestions=r.code_suggestions,
        detected_issues=r.detected_issues,
        raw_llm_response=r.raw_llm_response,
    ) for r in res_q]

# PUBLIC_INTERFACE
@app.get("/history", tags=["analysis"], response_model=List[AnalysisResultRead], summary="Get full analysis history for user")
def get_history(db: Session = Depends(get_db), current_user: models_module.User = Depends(get_current_user)):
    """
    Fetches the full analysis history for the logged-in user.
    """
    uploads = db.query(models_module.RepositoryUpload).filter(models_module.RepositoryUpload.user_id == current_user.id).all()
    all_res = []
    for upload in uploads:
        ars = db.query(models_module.AnalysisResult).filter(models_module.AnalysisResult.upload_id == upload.id).all()
        for r in ars:
            all_res.append(AnalysisResultRead(
                id=r.id,
                upload_id=r.upload_id,
                created_at=r.created_at,
                commit_message=r.commit_message,
                code_suggestions=r.code_suggestions,
                detected_issues=r.detected_issues,
                raw_llm_response=r.raw_llm_response,
            ))
    return sorted(all_res, key=lambda x: x.created_at, reverse=True)

# PUBLIC_INTERFACE
@app.get("/", summary="Health Check", tags=["repo"])
def health_check():
    """Simple health check endpoint."""
    return {"message": "Healthy"}

# Note: would likely want to add endpoints for logging out (token invalidation), deleting uploads, etc.
