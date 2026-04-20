from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from core.config import settings
from core.database import init_db
from api.routers import auth, projects, ideas, scripts, review

app = FastAPI(
    title="Nuro API",
    description="YouTube creator intelligence — idea gen, personalized scripting, and brain video review.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_origins != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(ideas.router, prefix="/api/v1")
app.include_router(scripts.router, prefix="/api/v1")
app.include_router(review.router, prefix="/api/v1")

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", include_in_schema=False)
def serve_frontend():
    index = static_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Nuro API running", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/health/detailed")
def health_detailed():
    from core.database import SessionLocal
    db_ok = False
    try:
        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db.close()
        db_ok = True
    except Exception:
        pass
    openai_key_set = bool(settings.openai_api_key)
    supabase_set = bool(settings.supabase_url and settings.supabase_service_role_key)
    return {
        "status": "ok" if (db_ok and openai_key_set) else "degraded",
        "version": "0.1.0",
        "environment": settings.environment,
        "checks": {
            "database": "ok" if db_ok else "error",
            "openai_key": "set" if openai_key_set else "missing",
            "supabase": "set" if supabase_set else "missing",
            "tribe_enabled": settings.tribe_enabled,
        },
    }


@app.on_event("startup")
def startup():
    init_db()
    Path("./temp_uploads").mkdir(parents=True, exist_ok=True)
