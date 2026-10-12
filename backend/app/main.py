import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.telephony import router as telephony_router
from app.database import initialize_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Personal Call Agent API",
    version="0.1.0",
    description="Call screening, caller rules, and optional Twilio voice webhooks.",
    lifespan=lifespan,
)


def get_allowed_origins() -> list[str]:
    default_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://0.0.0.0:5173",
        "http://0.0.0.0:5174",
    ]
    origins = default_origins.copy()
    for raw_origin in [os.getenv("FRONTEND_ORIGIN"), os.getenv("FRONTEND_ORIGINS")]:
        if raw_origin:
            origins.extend(item.strip().rstrip("/") for item in raw_origin.split(",") if item.strip())
    if os.getenv("RENDER"):
        origins.extend([
            "https://calling-agent-frontend.onrender.com",
            "https://calling-agent-api.onrender.com",
        ])
    return list(dict.fromkeys(origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_origin_regex=r"https://.*\.onrender\.com",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(api_router)
app.include_router(telephony_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "Personal Call Agent API", "docs": "/docs", "health": "/api/health"}