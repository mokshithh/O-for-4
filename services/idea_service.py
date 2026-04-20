"""
Idea Generation Service
Generates the top-5 ranked content ideas for a creator using dataset signals + GPT-4o.
"""

from __future__ import annotations
import json
import re
import time
import logging
from sqlalchemy.orm import Session

from models.project import Project, ProjectStatus
from models.script import IdeaOption
from services.claude_client import chat
from services.utils import parse_json_response

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


_signals_cache: dict[str, tuple[dict, float]] = {}
_SIGNALS_TTL = 300  # 5 minutes


def get_dataset_signals(niche: str, goal: str = "") -> dict:
    key = f"{niche}|{goal}"
    cached, ts = _signals_cache.get(key, ({}, 0.0))
    if cached and (time.time() - ts) < _SIGNALS_TTL:
        return cached
    try:
        from services.dataset.trend_alignment import get_trend_service
        result = get_trend_service().get_idea_signals(niche, goal)
    except Exception as exc:
        logger.warning("Dataset signals unavailable: %s", exc)
        result = _fallback_signals(niche, goal)
    _signals_cache[key] = (result, time.time())
    return result


def _fallback_signals(niche: str, goal: str) -> dict:
    """Hardcoded heuristics when the dataset service is unavailable."""
    niche_lower = niche.lower()
    goal_lower = goal.lower()

    if any(k in niche_lower for k in ["finance", "money", "wealth", "invest"]):
        patterns = ["problem/truth framing", "numbered list", "reveal/result"]
        formats = ["explainer", "story", "commentary"]
        notes = (
            "Personal finance videos perform best when they surface a painful truth or "
            "debunk a common myth. Numbered lists ('5 money mistakes') drive high click-through. "
            "Story-led videos ('How I paid off debt') outperform generic advice by 2-3x on retention."
        )
    elif any(k in niche_lower for k in ["fitness", "health", "workout"]):
        patterns = ["challenge/experiment", "problem/truth framing", "numbered list"]
        formats = ["challenge", "explainer", "story"]
        notes = (
            "Fitness channels that show real results and transformations get 3x more saves. "
            "Challenge formats ('I worked out every day for 30 days') consistently trend. "
            "Avoid generic 'workout tips' — specificity (exact routine, exact results) wins."
        )
    elif any(k in niche_lower for k in ["tech", "gadget", "software", "ai", "code"]):
        patterns = ["reveal/result", "question/curiosity", "problem/truth framing"]
        formats = ["review", "explainer", "commentary"]
        notes = (
            "Tech audiences reward specificity and honesty — reviews that call out flaws get "
            "more engagement than puff pieces. Opinion/commentary on AI trends is high-reach right now. "
            "Comparison videos ('X vs Y after 6 months') retain viewers longer than single-product reviews."
        )
    elif any(k in niche_lower for k in ["business", "entrepreneur", "startup"]):
        patterns = ["reveal/result", "problem/truth framing", "challenge/experiment"]
        formats = ["story", "explainer", "commentary"]
        notes = (
            "Business audiences engage most with real case studies and transparent breakdowns. "
            "Income reports and 'I built X in Y days' videos drive massive curiosity-gap clicks. "
            "Contrarian takes ('Why most business advice is wrong') outperform standard listicles."
        )
    else:
        patterns = ["problem/truth framing", "question/curiosity", "numbered list"]
        formats = ["explainer", "story", "commentary"]
        notes = (
            "Curiosity-gap titles consistently outperform descriptive ones across niches. "
            "Videos that promise a specific transformation or reveal outperform generic advice. "
            "Aim for titles 50-65 characters long — specific beats vague every time."
        )

    viral_goal = any(k in goal_lower for k in ["viral", "reach", "subscribers", "grow"])
    ranking = (
        f"Rank ideas using: 40% trend alignment with {patterns[0]} and {patterns[1]} patterns, "
        f"25% engagement potential for {niche} audience, 15% fit with goal '{goal}', "
        f"10% format confidence ({formats[0]}, {formats[1]}), 10% novelty. "
        f"{'Prioritise reach and shareability over depth.' if viral_goal else 'Prioritise retention and authority-building over raw reach.'}"
    )

    return {
        "source": "heuristic",
        "niche": niche,
        "top_title_pattern_labels": patterns,
        "top_content_format_labels": formats,
        "explanation_for_prompt": f"Data intelligence for '{niche}' (heuristic baseline):\n- Top performing title patterns: {', '.join(patterns)}\n- Top content formats: {', '.join(formats)}\n- Key insight: {notes}",
        "ranking_guidance": ranking,
    }


def _extract_json_array(raw: str) -> list:
    """Extract a JSON array from LLM output, delegating fence stripping to shared util."""
    try:
        result = parse_json_response(raw)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "ideas" in result:
            return result["ideas"]
    except (json.JSONDecodeError, ValueError):
        pass

    # Last resort: find first [...] block
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON array from LLM response. Raw (first 300 chars): {raw[:300]}")


def generate_ideas(project: Project, db: Session) -> list[IdeaOption]:
    """Generate top-5 ideas via GPT-4o using dataset signals, then persist them."""
    ds = get_dataset_signals(project.niche or "", project.goal or "")
    ds_block = ds.get("explanation_for_prompt", "")
    ranking_guidance = ds.get("ranking_guidance", "")

    data_section = ""
    if ds_block:
        data_section = f"\nDataset intelligence:\n{ds_block}\n\nRanking guidance: {ranking_guidance}\n"

    system = (
        "You are an elite YouTube content strategist who has studied thousands of viral videos. "
        "You understand niche trends, thumbnail psychology, hook structure, and audience retention. "
        "You give specific, creator-ready advice — not generic platitudes. "
        "Output must be a valid JSON array only. No markdown fences. No commentary before or after."
    )

    prompt = f"""Creator profile:
- Niche: {project.niche}
- Tone: {project.tone}
- Target audience: {project.target_audience}
- Goal: {project.goal}
- Video style: {project.video_style}
- Intended duration: {project.intended_duration}
{data_section}
Generate exactly 5 ranked YouTube video ideas for this creator. Each idea must be tailored to this specific creator's niche, voice, and audience — not generic advice they could Google.

Return a JSON array with exactly this structure:
[
  {{
    "rank": 1,
    "title": "The full compelling YouTube video title (50-65 characters ideal)",
    "hook": "The exact opening 1-2 sentences to say on camera that makes the viewer stay",
    "explanation": "2-3 sentences explaining WHY this specific idea will perform well for this creator and audience",
    "trend_alignment": "1-2 sentences on how this taps into current patterns that drive views and retention in this niche"
  }}
]

Ranking rules:
- Rank 1 = highest predicted performance (strongest title pattern + best audience fit)
- Titles must be specific and curiosity-driven — never vague or generic
- The hook field should be an actual script line, not a description of a hook
- Return ONLY the JSON array, nothing else"""

    try:
        raw = chat(system=system, user=prompt, max_tokens=2500)
    except Exception as exc:
        logger.error("OpenAI call failed: %s", exc)
        raise RuntimeError(f"AI service error: {exc}") from exc

    try:
        ideas_data = _extract_json_array(raw)
    except Exception as exc:
        logger.error("JSON parse failed. Raw response: %s", raw[:500])
        raise ValueError(f"AI returned invalid format: {exc}") from exc

    if not ideas_data:
        raise ValueError("AI returned empty ideas list")

    # Clear old ideas for this project
    db.query(IdeaOption).filter(IdeaOption.project_id == project.id).delete()

    idea_objects = []
    for i, idea_data in enumerate(ideas_data[:5]):
        idea = IdeaOption(
            project_id=project.id,
            rank=idea_data.get("rank", i + 1),
            title=idea_data.get("title", f"Idea {i+1}"),
            hook=idea_data.get("hook"),
            explanation=idea_data.get("explanation"),
            trend_alignment=idea_data.get("trend_alignment"),
            dataset_signals=ds,
        )
        db.add(idea)
        idea_objects.append(idea)

    project.status = ProjectStatus.ideas_generated
    db.commit()
    for idea in idea_objects:
        db.refresh(idea)

    return idea_objects
