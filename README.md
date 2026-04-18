# Placeholdr

YouTube creator intelligence tool — idea generation, personalized scripting, and brain video review.

## Stack

- **Backend:** FastAPI + SQLAlchemy (SQLite → Postgres-ready)
- **AI:** Anthropic Claude (idea gen, scripting, coaching)
- **Brain analysis:** TRIBE v2 adapter (mock fallback active by default)
- **Transcript:** OpenAI Whisper
- **Video fetch:** yt-dlp

## Quick Start

```bash
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env

pip install fastapi uvicorn sqlalchemy passlib[bcrypt] python-jose[cryptography] \
  python-multipart pydantic[email] pydantic-settings anthropic yt-dlp httpx aiofiles python-dotenv

uvicorn main:app --reload
```

Open `http://localhost:8000` for the frontend, or `http://localhost:8000/docs` for the API.

## API Routes

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/signup` | Create account |
| POST | `/api/v1/auth/login` | Login |
| GET | `/api/v1/auth/me` | Current user |
| POST | `/api/v1/projects` | Create project (creator setup) |
| GET | `/api/v1/projects` | List projects |
| POST | `/api/v1/projects/{id}/ideas/generate` | Generate top-5 ideas |
| POST | `/api/v1/projects/{id}/ideas/select` | Select idea + get personalization Qs |
| POST | `/api/v1/projects/{id}/ideas/personalize` | Submit personalization answers |
| POST | `/api/v1/projects/{id}/scripts/generate` | Generate personalized script |
| GET | `/api/v1/projects/{id}/scripts/active` | Get active script |
| PATCH | `/api/v1/projects/{id}/scripts/{sid}/edit` | Save user edits |
| POST | `/api/v1/projects/{id}/scripts/{sid}/revise` | AI revision |
| POST | `/api/v1/projects/{id}/review/upload` | Upload video file |
| POST | `/api/v1/projects/{id}/review/youtube` | Submit YouTube URL |
| GET | `/api/v1/projects/{id}/review/{rid}/status` | Poll review status |
| GET | `/api/v1/projects/{id}/review/{rid}` | Get full review results |

## TRIBE v2 Integration

To activate the real model:

1. `git clone https://github.com/facebookresearch/tribev2 brain/tribe_v2`
2. Download pretrained weights to `brain/tribe_v2/pretrained/`
3. Set `TRIBE_ENABLED=true` in `.env`
4. Complete `brain/tribe_adapter.py` — the `load()` and `analyze()` stubs are ready

When disabled, `brain/mock_brain.py` generates plausible attention curves as fallback.

## Architecture

```
api/routers/     — FastAPI route handlers (thin, delegates to services)
services/        — Business logic (idea_service, script_service, review_service, video_service, transcript_service)
brain/           — TRIBE v2 adapter + mock + orchestration service
models/          — SQLAlchemy ORM models
schemas/         — Pydantic request/response schemas
core/            — Config, database, security
static/          — Basic frontend (replace with Stitch build)
```

## Dataset Integration (Future)

Two stubs are ready for dataset-backed signals:

- `services/idea_service.py → get_dataset_signals()`
- `services/script_service.py → get_dataset_script_signals()`

Both currently return `{"status": "stub"}`. Replace with real dataset queries when the pipeline is ready.
