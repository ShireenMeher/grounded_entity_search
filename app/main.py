import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version=settings.app_version)

# Allow localhost for dev + any deployed frontend URL set via env var
_extra = os.getenv("ALLOWED_ORIGIN", "")
ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
if _extra:
    ALLOWED_ORIGINS.append(_extra)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)