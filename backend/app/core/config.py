import os
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "Multi-Source AI Research Engine"
    API_V1_STR: str = "/api"
    DATABASE_URL: str = "sqlite:///./research_engine.db"
    
    # Rate limits and timeouts
    REQUEST_TIMEOUT_SECONDS: float = 12.0
    MAX_CONCURRENT_REQUESTS: int = 5
    DEFAULT_RESULT_LIMIT: int = 20
    
    # Optional API Keys (none strictly required for initial free tier sources)
    GITHUB_TOKEN: str | None = None
    STACKEXCHANGE_KEY: str | None = None
    # Reddit OAuth & API Configuration
    REDDIT_CLIENT_ID: str | None = None
    REDDIT_CLIENT_SECRET: str | None = None
    REDDIT_USER_AGENT: str = "python:multi-source-research-engine:v1.0.0 (by /u/app_developer)"
    REDDIT_RATE_LIMIT_PER_MINUTE: int = 30 # default standard unauthenticated/app-only quota limit
    
    # Kaggle API Credentials (KAGGLE_USERNAME and KAGGLE_KEY)
    KAGGLE_USERNAME: str | None = None
    KAGGLE_KEY: str | None = None

    # OpenAlex API (Optional API Key for elevated rate limits / polite pool)
    OPENALEX_API_KEY: str | None = None
    OPENALEX_EMAIL: str | None = None

    # Crossref API (Polite pool contact email)
    CROSSREF_MAILTO: str | None = "researcher@example.com"

    # Optional OpenAI / LLM key
    OPENAI_API_KEY: str | None = None
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000"
    ]

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
