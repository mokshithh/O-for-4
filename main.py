from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from core.database import init_db
from api.routers import auth, projects, ideas, scripts, review

app = FastAPI(
    title="Placeholdr API",
    description="YouTube creator intelligence — idea gen, personalized scripting, and brain video review.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
    return {"message": "Placeholdr API running", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.on_event("startup")
def startup():
    init_db()
    Path("./temp_uploads").mkdir(parents=True, exist_ok=True)
