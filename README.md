# Nuro — Creator Intelligence Platform

> AI-powered YouTube creator tool: trend-aware idea generation, personalized scripting, and brain-engagement video review — all in one flow.

**Live demo:** https://placeholdr-g18c.onrender.com

---

## Team

| Name | Role |
|------|------|
| Anhad | Video Production and Submission |
| Atharva | Data Analysis and Cleaning |
| Hariesh | Front End Designing |
| Mokshith | Backend + Everything Else |

---

## Problem

YouTube creators face three compounding problems:

1. **Idea paralysis** — No signal on what will actually perform in their niche. They guess.
2. **Generic scripts** — Generic AI tools give generic output. The result sounds like everyone else.
3. **Blind uploads** — Creators have no way to know if their video will retain viewers before it goes live. They find out from the analytics — too late.

---

## Solution

Nuro is a three-stage intelligence pipeline:

```
Idea Generation → Personalized Script → Brain Video Review
```

Each stage is informed by real YouTube trending data, the creator's specific profile (niche, tone, audience, goal), and GPT-4o reasoning — not generic prompts.

**Flow A (full pipeline):** Ideas → Select + personalize → Script → Record → Upload for review  
**Flow B (review only):** Skip ideation, upload an existing video directly for scoring

---

## Key Features

### 1. Trend-Aware Idea Generation
- Analyses creator profile (niche, tone, audience, goal, style, duration)
- Pulls signals from a 141MB YouTube trending dataset — title pattern classification, engagement rates, format confidence, saturation levels
- GPT-4o ranks 5 ideas by predicted performance: hook quality, trend alignment, niche fit
- Each idea includes: title, exact opening hook script line, explanation, trend alignment rationale

### 2. Personalized Script Generation
- 6 personalization questions capture the creator's unique angle, authority, tone, main point, viewer outcome
- GPT-4o generates a structured script: hook → acts → CTA
- Full edit + AI revision loop on the script before recording

### 3. Meta Tribe v2 Brain Video Review
- Upload the recorded video (MP4/MOV/etc.)
- OpenAI Whisper API extracts the transcript and segments it by timestamp
- GPT-4o simulates per-segment brain engagement: attention continuity, hook strength, pacing, novelty
- Scores across 4 dimensions: **Niche Fit**, **Retention Potential**, **Brain Engagement**, **Virality Potential**
- Each score is benchmarked against the niche dataset average
- Coaching feedback + improvement suggestions generated per video
- Real-time processing log with stage-by-stage progress display
- 3D animated brain visualization (Three.js WebGL) shows live attention state

### 4. Dataset Intelligence
- `youtube_trending_cleaned.csv` (~141MB, 17MB compressed) committed to repo as `.xz` and decompressed at build time
- `PatternClassifier` — regex-based title pattern detection (problem/truth, numbered list, reveal/result, curiosity gap, challenge/experiment)
- `TrendAlignmentService` — niche stats (median engagement, P75 threshold, row counts), pattern rankings, saturation levels
- All AI prompts are enriched with these signals — idea generation, script scoring, and review scoring

---

## Architecture

```
nuro/
├── main.py                          # FastAPI app entry point
├── render.yaml                      # Render deployment config (build + env)
├── requirements.txt
│
├── api/
│   └── routers/
│       ├── auth.py                  # Signup / login / JWT refresh
│       ├── projects.py              # Project CRUD
│       ├── ideas.py                 # Idea generation + selection + personalization
│       ├── scripts.py               # Script generation, edit, revision
│       └── review.py                # Video upload, processing, results polling
│
├── services/
│   ├── claude_client.py             # OpenAI GPT-4o wrapper (temperature=0, seed=42)
│   ├── idea_service.py              # Idea generation pipeline + dataset signals
│   ├── script_service.py            # Script generation pipeline
│   ├── review_service.py            # Full review pipeline (transcription → scoring)
│   ├── transcript_service.py        # Whisper API + segment extraction
│   ├── video_service.py             # Video file handling, duration extraction
│   ├── title_service.py             # Title analysis utilities
│   └── dataset/
│       ├── loader.py                # CSV loader, niche stats (DatasetLoader)
│       ├── pattern_classifier.py    # Title pattern + format classification
│       └── trend_alignment.py       # TrendAlignmentService — idea + review signals
│
├── brain/
│   ├── service.py                   # BrainService — routes to TRIBE v2 or mock
│   ├── tribe_adapter.py             # Meta Tribe v2 integration adapter (stub-ready)
│   ├── mock_brain.py                # Fallback engagement curve generator
│   └── tribe_v2/                    # Meta Tribe v2 submodule (fMRI model)
│
├── models/
│   ├── user.py                      # User ORM model
│   ├── project.py                   # Project + ProjectStatus
│   ├── script.py                    # Script + IdeaOption ORM models
│   └── review.py                    # VideoReview + ReviewSegment ORM models
│
├── schemas/
│   ├── auth.py                      # Login / signup request/response schemas
│   ├── project.py                   # Project create/read schemas
│   ├── ideas.py                     # Idea generation + selection schemas
│   ├── script.py                    # Script generation + edit schemas
│   └── review.py                    # Review submit + result schemas
│
├── core/
│   ├── config.py                    # Pydantic settings (env vars)
│   ├── database.py                  # SQLAlchemy engine + session factory
│   └── security.py                  # JWT + Supabase JWKS verification
│
├── static/
│   └── index.html                   # Single-page frontend (vanilla JS/CSS, no framework)
│                                    # Three.js 3D brain viz, animated stepper, live polling
│
├── youtube_trending_cleaned.csv.xz  # Compressed trending dataset (17MB → 141MB at build)
└── test_playwright.py               # End-to-end Playwright test suite (17 tests)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI 0.110 + SQLAlchemy 2.0 (SQLite, Postgres-ready) |
| AI — Ideas / Scripts / Review | OpenAI GPT-4o (`temperature=0`, `seed=42` for determinism) |
| Transcription | OpenAI Whisper API |
| Brain model | Meta Tribe v2 (fMRI-trained; GPT-4o simulation as active fallback) |
| Auth | Supabase JWT (ES256 JWKS verification) |
| Dataset | YouTube Trending CSV — pattern classification + niche benchmarks |
| Frontend | Vanilla HTML/JS/CSS — no framework; Three.js WebGL brain visualization |
| Deployment | Render (free tier, auto-deploy on push) |
| Testing | Playwright (sync API, 17 end-to-end tests) |

---

## Dataset

`youtube_trending_cleaned.csv.xz` is committed to this repo in LZMA-compressed form.

At build time, Render decompresses it:
```bash
python -c "import lzma, shutil; shutil.copyfileobj(lzma.open('youtube_trending_cleaned.csv.xz'), open('data/youtube_trending.csv','wb'))"
```

The dataset powers:
- Title pattern classification (7 pattern types ranked by engagement)
- Niche-level engagement benchmarks (median, P75)
- Saturation detection (low / medium / high)
- Format confidence scoring (explainer, story, challenge, review, commentary)

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/signup` | Create account |
| POST | `/api/v1/auth/login` | Login, returns JWT |
| GET | `/api/v1/auth/me` | Current user info |
| POST | `/api/v1/projects` | Create project (niche, tone, audience, goal, style, duration) |
| GET | `/api/v1/projects` | List all projects |
| POST | `/api/v1/projects/{id}/ideas/generate` | Generate 5 ranked ideas |
| POST | `/api/v1/projects/{id}/ideas/select` | Select idea, get personalization questions |
| POST | `/api/v1/projects/{id}/ideas/personalize` | Submit answers, trigger script generation |
| POST | `/api/v1/projects/{id}/scripts/generate` | Generate personalized script |
| GET | `/api/v1/projects/{id}/scripts/active` | Get current script |
| PATCH | `/api/v1/projects/{id}/scripts/{sid}/edit` | Save manual edits |
| POST | `/api/v1/projects/{id}/scripts/{sid}/revise` | AI revision with instructions |
| POST | `/api/v1/projects/{id}/review/upload` | Upload video file for review |
| GET | `/api/v1/projects/{id}/review/{rid}/progress` | Poll live processing stages |
| GET | `/api/v1/projects/{id}/review/{rid}` | Get full review results |

---

## Local Setup

```bash
git clone https://github.com/mokshithh/O-for-4.git
cd O-for-4

cp .env.example .env
# Fill in: OPENAI_API_KEY, SECRET_KEY, SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY

pip install -r requirements.txt

# Decompress dataset
python -c "import lzma, shutil; shutil.copyfileobj(lzma.open('youtube_trending_cleaned.csv.xz'), open('data/youtube_trending.csv','wb'))"

uvicorn main:app --reload --port 8765
```

Open `http://localhost:8765` — frontend auto-served from `static/index.html`.  
API docs at `http://localhost:8765/docs`.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | GPT-4o + Whisper API key |
| `SECRET_KEY` | Yes | JWT signing secret (any random string) |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes | Supabase anon key (frontend auth) |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Supabase service role key (server auth) |
| `DATABASE_URL` | No | Defaults to `sqlite:///./placeholdr.db` |
| `TRIBE_ENABLED` | No | Set `true` to activate Meta Tribe v2 model |

---

## Meta Tribe v2 Integration

The `brain/tribe_v2/` directory contains the Meta Tribe v2 fMRI model submodule. The integration adapter (`brain/tribe_adapter.py`) is stub-ready:

1. Ensure `brain/tribe_v2/` is populated (run `git submodule update --init`)
2. Download pretrained weights to `brain/tribe_v2/pretrained/`
3. Set `TRIBE_ENABLED=true` in `.env`
4. Implement `load()` and `analyze()` in `brain/tribe_adapter.py`

When `TRIBE_ENABLED` is false (default), `brain/mock_brain.py` generates plausible engagement curves and GPT-4o simulation runs as fallback — all review features remain fully functional.

---

## Testing

```bash
# Start the server first
uvicorn main:app --port 8765

# Run Playwright suite (17 tests)
python test_playwright.py
```

Tests cover: auth flow, dashboard, Flow A (ideas → script), Flow B (direct review), stepper navigation, review screen UI, score rendering, and JS console error detection.
