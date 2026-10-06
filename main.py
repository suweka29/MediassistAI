"""
MediAssistAI - FastAPI Backend
===============================
REST API for the symptom-checker chatbot.

Endpoints
---------
GET  /api/health                    liveness + model metadata
POST /api/auth/register             create an account
POST /api/auth/login                log in, get a bearer token
POST /api/auth/logout               invalidate a bearer token
GET  /api/auth/me                   current logged-in user info
POST /api/session                   start a new chat session   (auth required)
POST /api/chat                      send a message              (auth required)
GET  /api/session/{sid}/history     message history for a session (auth required)
POST /api/session/{sid}/reset       reset a session (keep same id) (auth required)

Run:
    uvicorn backend.main:app --reload --port 8000
(run from the MediAssistAI/ project root so imports resolve)
"""
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional

from backend import database as db
from backend import chat_engine
from backend import auth

FRONTEND_DIR = os.path.join(ROOT, "frontend")

app = FastAPI(title="MediAssistAI", version="1.1.0",
             description="Educational AI symptom-checker chatbot API. "
                         "Not a substitute for professional medical advice.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    db.init_db()
    # Warm up the ML engine at startup instead of on first request so the
    # first chat message isn't slow.
    chat_engine.get_engine()


def require_user(authorization: Optional[str] = Header(None)) -> str:
    """FastAPI dependency: validates the `Authorization: Bearer <token>`
    header and returns the logged-in username, or raises 401."""
    username = auth.current_username(authorization)
    if not username:
        raise HTTPException(status_code=401, detail="not authenticated")
    return username


# --------------------------------------------------------------------------- schemas
class SessionCreate(BaseModel):
    age: int = Field(35, ge=0, le=120)
    gender: str = Field("male", pattern="^(male|female)$")
    duration_days: int = Field(3, ge=0, le=60)
    severity: int = Field(5, ge=1, le=10)


class ChatMessage(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=2000)


class RegisterBody(BaseModel):
    username: str
    password: str
    display_name: str = ""


class LoginBody(BaseModel):
    username: str
    password: str


# ----------------------------------------------------------------------- auth routes
@app.post("/api/auth/register")
def register(body: RegisterBody):
    err = auth.register(body.username, body.password, body.display_name)
    if err:
        raise HTTPException(status_code=400, detail=err)
    token, display_name = auth.login(body.username, body.password)
    return {"token": token, "username": body.username,
            "display_name": display_name}


@app.post("/api/auth/login")
def login(body: LoginBody):
    token, display_name = auth.login(body.username, body.password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {"token": token, "username": body.username,
            "display_name": display_name}


@app.post("/api/auth/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        auth.logout(authorization[len("Bearer "):].strip())
    return {"status": "ok"}


@app.get("/api/auth/me")
def me(username: str = Depends(require_user)):
    user = db.get_user(username)
    return {"username": username,
            "display_name": user["display_name"] if user else username}


# --------------------------------------------------------------------------- routes
@app.get("/api/health")
def health():
    engine = chat_engine.get_engine()
    return {
        "status": "ok",
        "model_classes": len(engine.metadata["classes"]),
        "model_trained_at": engine.metadata["trained_at"],
        "architecture": engine.metadata["architecture"],
        "test_accuracy": engine.metadata["metrics"]["test_accuracy"],
    }


@app.post("/api/session")
def create_session(body: SessionCreate, username: str = Depends(require_user)):
    result = chat_engine.start_session(
        age=body.age, gender=body.gender,
        duration_days=body.duration_days, severity=body.severity,
        username=username)
    return result


@app.post("/api/chat")
def chat(body: ChatMessage, username: str = Depends(require_user)):
    session = db.get_session(body.session_id)
    if session is None or session.get("username") != username:
        raise HTTPException(status_code=404, detail="session not found")
    try:
        return chat_engine.handle_message(body.session_id, body.message)
    except ValueError:
        raise HTTPException(status_code=404, detail="session not found")


@app.get("/api/session/{sid}/history")
def history(sid: str, username: str = Depends(require_user)):
    session = db.get_session(sid)
    if session is None or session.get("username") != username:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session": session, "messages": db.get_history(sid)}


@app.post("/api/session/{sid}/reset")
def reset(sid: str, body: SessionCreate = SessionCreate(),
         username: str = Depends(require_user)):
    session = db.get_session(sid)
    if session is None or session.get("username") != username:
        raise HTTPException(status_code=404, detail="session not found")
    return chat_engine.reset_session(
        sid, age=body.age, gender=body.gender,
        duration_days=body.duration_days, severity=body.severity)


# --------------------------------------------------------------------------- frontend
def _file_version(path: str) -> str:
    """Short content hash used to cache-bust static assets so a browser
    that has an old app.js/style.css cached always picks up new code
    after this project is updated, without needing a manual hard-refresh."""
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:8]
    except OSError:
        return "0"


def _serve_versioned(filename: str) -> HTMLResponse:
    with open(os.path.join(FRONTEND_DIR, filename), encoding="utf-8") as f:
        html = f.read()
    for asset in ("app.js", "style.css", "login.js"):
        path = os.path.join(FRONTEND_DIR, asset)
        if os.path.exists(path):
            v = _file_version(path)
            html = html.replace(f'/static/{asset}', f'/static/{asset}?v={v}')
    return HTMLResponse(html)


if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.middleware("http")
    async def _no_cache_static(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/") or request.url.path in ("/", "/login"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    @app.get("/")
    def index():
        return _serve_versioned("index.html")

    @app.get("/login")
    def login_page():
        return _serve_versioned("login.html")
