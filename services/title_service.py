"""
Title Suggestion Service
========================
Generates dataset-backed trending title suggestions from a completed review.
"""
from __future__ import annotations
import json
import logging
from sqlalchemy.orm import Session

from models.review import VideoReview
from models.project import Project
from services.claude_client import chat

logger = logging.getLogger(__name__)


def generate_title_suggestions(review: VideoReview, project: Project) -> list[dict]:
    """Return 5 title suggestions ranked by predicted CTR lift."""
    # Pull dataset signals for the niche
    ds_context = ""
    try:
        from services.dataset.trend_alignment import get_trend_service
        svc = get_trend_service()
        signals = svc.get_idea_signals(project.niche or "", project.goal or "")
        top_patterns = signals.get("top_title_patterns", [])
        top_formats = signals.get("top_content_formats", [])
        median_eng = signals.get("median_engagement_rate", "")
        p90_eng = signals.get("p90_engagement_rate", "")
        ds_context = (
            f"Dataset signals for '{project.niche}':\n"
            f"- Top performing title patterns: {', '.join(top_patterns)}\n"
            f"- Top content formats: {', '.join(top_formats)}\n"
            f"- Median engagement rate: {median_eng} | P90: {p90_eng}\n"
        )
    except Exception as exc:
        logger.warning("Dataset signals unavailable: %s", exc)

    transcript_snippet = (review.transcript or "")[:800]
    overall = review.overall_score or 0
    coaching = review.coaching_feedback or ""

    system = (
        "You are a YouTube title strategist who specialises in CTR optimisation. "
        "You generate titles that combine proven viral patterns with the creator's actual content. "
        "Output must be valid JSON only — no markdown, no commentary."
    )

    prompt = f"""
Creator profile:
- Niche: {project.niche}
- Target audience: {project.target_audience}
- Tone: {project.tone}
- Goal: {project.goal}

Video review data:
- Overall score: {overall}/100
- Coaching feedback: {coaching}
- Transcript excerpt: {transcript_snippet}

{ds_context}

Generate exactly 5 title suggestions optimised for maximum CTR and watch time in this niche.
Each title must use a different pattern (question, number list, problem/truth, challenge, reveal).

Return a JSON array:
[
  {{
    "title": "Full optimised title",
    "pattern": "question_curiosity | number_list | problem_truth | challenge_experiment | reveal_result",
    "hook_angle": "One sentence on what makes this title compelling",
    "predicted_ctr_score": <int 60-99>,
    "why": "One sentence citing dataset pattern or engagement signal"
  }},
  ...
]

Rules:
- Titles must be specific to THIS video's content — no generic placeholders
- Use the creator's niche language and audience expectations
- Rank by predicted_ctr_score descending
- Return ONLY the JSON array
"""

    raw = chat(system=system, user=prompt, max_tokens=1500, temperature=0.3)
    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as exc:
        logger.error("Title suggestions parse failed: %s", exc)
        return []
