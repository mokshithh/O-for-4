"""
Idea Generation Service
=======================
Generates the top-5 ranked content ideas for a creator.

Dataset integration boundary:
  - get_dataset_signals() is the stub to plug in real dataset-backed signals.
  - Currently returns empty dict; replace with real dataset query when available.
"""

from __future__ import annotations
import json
import logging
from typing import Optional
from sqlalchemy.orm import Session

from models.project import Project, ProjectStatus
from models.script import IdeaOption
from services.claude_client import chat

logger = logging.getLogger(__name__)

PERSONALIZATION_QUESTIONS = [
    {
        "id": "angle",
        "question": "What is your personal angle on this topic?",
        "hint": "Your unique perspective, opinion, or take that makes this different from other videos on the same topic.",
    },
    {
        "id": "authority",
        "question": "What experience, story, or authority do you have here?",
        "hint": "Why should viewers trust your take? Personal experience, expertise, or a compelling story counts.",
    },
    {
        "id": "style",
        "question": "Should this feel educational, story-led, opinion-led, or challenge-based?",
        "hint": "Pick the primary presentation style for this specific video.",
    },
    {
        "id": "main_point",
        "question": "What is the one main point you want the viewer to remember?",
        "hint": "If they forget everything else, what is the single takeaway?",
    },
    {
        "id": "viewer_outcome",
        "question": "What outcome do you want from the viewer after watching?",
        "hint": "Subscribe, change a belief, take action, share the video — be specific.",
    },
    {
        "id": "tone",
        "question": "What tone should this specific video use?",
        "hint": "Casual, intense, curious, confrontational, warm, funny — different from your general channel tone is fine.",
    },
]


def get_dataset_signals(niche: str, ideas_context: str) -> dict:
    """
    STUB: returns dataset-backed trend signals for idea scoring.
    Replace with real dataset query when the dataset pipeline is ready.
    """
    return {
        "status": "stub",
        "message": "Dataset-backed signals not yet active.",
        "niche": niche,
    }


def generate_ideas(project: Project, db: Session) -> list[IdeaOption]:
    """Generate top-5 ideas via Claude and persist them."""
    system = (
        "You are a YouTube content strategist who specialises in long-form video performance. "
        "You analyse niche trends, audience psychology, and what makes videos retain viewers. "
        "Output must be valid JSON only — no markdown fences, no commentary."
    )

    prompt = f"""
Creator profile:
- Channel URL: {project.channel_url}
- Niche: {project.niche}
- Tone: {project.tone}
- Target audience: {project.target_audience}
- Goal: {project.goal}
- Video style: {project.video_style}
- Intended duration: {project.intended_duration}

Generate exactly 5 ranked content ideas for this creator. Return a JSON array with this structure:
[
  {{
    "rank": 1,
    "title": "Full video title",
    "hook": "One sentence describing the compelling opening hook",
    "explanation": "2-3 sentences on why this idea will perform well for this creator",
    "trend_alignment": "1-2 sentences on how this aligns with current long-form trends in this niche"
  }},
  ...
]

Requirements:
- Ideas must be ranked from strongest (1) to good (5)
- Each idea must be specific to this creator's niche, goal, and audience
- Titles should be compelling and optimised for YouTube click-through
- The explanation should sound like a savvy creator strategist, not a corporate AI
- Return ONLY the JSON array
"""

    raw = chat(system=system, user=prompt, max_tokens=2000)

    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        ideas_data = json.loads(raw)
    except Exception as exc:
        logger.error("Failed to parse ideas JSON: %s\nRaw: %s", exc, raw[:500])
        raise ValueError("Idea generation returned invalid JSON") from exc

    # Clear old ideas for this project
    db.query(IdeaOption).filter(IdeaOption.project_id == project.id).delete()

    idea_objects = []
    dataset_signals = get_dataset_signals(project.niche or "", str(ideas_data))

    for idea_data in ideas_data[:5]:
        idea = IdeaOption(
            project_id=project.id,
            rank=idea_data["rank"],
            title=idea_data["title"],
            hook=idea_data.get("hook"),
            explanation=idea_data.get("explanation"),
            trend_alignment=idea_data.get("trend_alignment"),
            dataset_signals=dataset_signals,
        )
        db.add(idea)
        idea_objects.append(idea)

    project.status = ProjectStatus.ideas_generated
    db.commit()
    for idea in idea_objects:
        db.refresh(idea)

    return idea_objects
