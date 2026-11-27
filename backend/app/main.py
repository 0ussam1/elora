import os
import sys
from pathlib import Path

# Ensure backend directory is in sys.path when launched from repository root (e.g. FastAPI Cloud)
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.database.session import engine, Base, SessionLocal
from app.api.endpoints import router as api_router
from app.api.discovery_endpoints import router as discovery_router
from app.services.news_service import NewsService
import app.models.database # ensure models are registered with Base

# Create tables if not existing
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: seed default news feeds in database
    try:
        with SessionLocal() as db:
            NewsService.seed_default_feeds(db)
    except Exception:
        pass
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Multi-Source AI Research Engine REST API with Evidence Traceability",
    version="1.0.0",
    lifespan=lifespan
)

# CORS — allow localhost for dev + any Vercel domain for production
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]

# Add production frontend URL from env var if set
frontend_url = os.environ.get("FRONTEND_URL", "")
if frontend_url:
    allowed_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",  # allow all Vercel preview URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(discovery_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {
        "message": "Welcome to ELORA API",
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
