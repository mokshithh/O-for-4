"""
Script Generation Service
=========================
Generates personalized scripts and script-stage brain predictions.

Dataset integration boundary:
  - get_dataset_script_signals() is the stub to plug in real dataset backing.
"""

from __future__ import annotations
import json
import logging
from sqlalchemy.orm import Session

from models.project import Project, ProjectStatus
from models.script import Script, IdeaOption
from services.claude_client import chat

logger = logging.getLogger(__name__)


def get_dataset_script_signals(niche: str, title: str, goal: str = "") -> dict:
    """Dataset-backed trend signals for script generation via TrendAlignmentService."""
    try:
        from services.dataset.trend_alignment import get_trend_service
        return get_trend_service().get_script_signals(niche, title, goal)
    except Exception as exc:
        logger.warning("Script dataset signals failed: %s", exc)
        return {"source": "unavailable", "niche": niche, "title": title}


def generate_script(project: Project, idea: IdeaOption, db: Session) -> Script:
    """Generate a personalized script for the selected idea and save it."""
    answers = project.personalization_answers or {}
    ds = get_dataset_script_signals(project.niche or "", idea.title or "", project.goal or "")
    ds_block = ds.get("explanation_for_prompt", "")

    system = (
        "You are a world-class YouTube script writer who creates content that holds attention "
        "for 10-20 minutes. You write like a smart creator coach: direct, human, and practical. "
        "Output must be valid JSON only — no markdown fences, no extra commentary."
    )

    prompt = f"""
Creator profile:
- Niche: {project.niche}
- Tone: {project.tone}
- Target audience: {project.target_audience}
- Goal: {project.goal}
- Video style: {project.video_style}
- Intended duration: {project.intended_duration}

Selected idea: {idea.title}
Idea context: {idea.explanation}

{f"Dataset intelligence:{chr(10)}{ds_block}" if ds_block else ""}

Creator personalization answers:
- Personal angle: {answers.get('angle', 'Not provided')}
- Authority/experience: {answers.get('authority', 'Not provided')}
- Presentation style: {answers.get('style', 'Not provided')}
- Main point to remember: {answers.get('main_point', 'Not provided')}
- Desired viewer outcome: {answers.get('viewer_outcome', 'Not provided')}
- Tone for this video: {answers.get('tone', 'Not provided')}

Generate a complete, tailored script. Return a JSON object with this structure:
{{
  "title": "Final video title",
  "hook": "The exact opening 30-60 seconds of the script",
  "segments": [
    {{
      "title": "Segment name",
      "content": "Full scripted content for this segment",
      "duration_estimate": "~X minutes"
    }}
  ],
  "cta": "Call to action script",
  "pacing_notes": "Notes about pacing, energy shifts, and delivery advice",
  "trend_match_score": <float 0-100>,
  "trend_match_explanation": "Why this script aligns with high-performing patterns in this niche",
  "brain_prediction": {{
    "trend_match_score": <float 0-100>,
    "audience_fit_score": <float 0-100>,
    "hook_strength_score": <float 0-100>,
    "retention_risk_score": <float 0-100>,
    "format_confidence_score": <float 0-100>,
    "novelty_score": <float 0-100>,
    "predicted_retention_drops": ["segment name(s) likely to lose viewers"],
    "summary": "2-3 sentences of blunt pre-production prediction"
  }}
}}

Requirements:
- Script must feel personalised to THIS creator — use their angle, authority, and answers
- Hook must open with tension, a question, or a pattern interrupt — no generic intros
- Each segment should flow into the next with clear transitions
- Pacing notes should be specific and actionable
- Brain prediction must be honest — flag real weaknesses, not just positives
- Return ONLY the JSON object
"""

    raw = chat(system=system, user=prompt, max_tokens=4000)

    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
    except Exception as exc:
        logger.error("Script JSON parse failed: %s\nRaw: %s", exc, raw[:500])
        raise ValueError("Script generation returned invalid JSON") from exc

    # Deactivate old scripts for this project
    db.query(Script).filter(Script.project_id == project.id).update({"is_active": False})

    full_script_parts = [data.get("hook", "")]
    for seg in data.get("segments", []):
        full_script_parts.append(f"\n\n## {seg['title']}\n{seg['content']}")
    full_script_parts.append(f"\n\n## CTA\n{data.get('cta', '')}")
    full_script = "\n".join(full_script_parts)

    script = Script(
        project_id=project.id,
        idea_id=idea.id,
        version=1.0,
        is_active=True,
        title=data.get("title"),
        hook=data.get("hook"),
        full_script=full_script,
        segment_outline=data.get("segments"),
        cta=data.get("cta"),
        pacing_notes=data.get("pacing_notes"),
        trend_match_score=data.get("trend_match_score"),
        trend_match_explanation=data.get("trend_match_explanation"),
        brain_prediction=data.get("brain_prediction"),
    )
    db.add(script)
    project.status = ProjectStatus.script_generated
    db.commit()
    db.refresh(script)
    return script


def revise_script(script: Script, instructions: str, db: Session) -> Script:
    """Generate a revised version of the script based on user instructions."""
    system = (
        "You are a YouTube script editor. You revise scripts based on specific creator instructions. "
        "Keep the creator's voice and personalisation intact. "
        "Return only the revised full script text — no JSON, no headers, just the script."
    )

    prompt = f"""
Original script:
{script.user_edited_content or script.full_script}

Revision instructions:
{instructions}

Return the revised complete script.
"""

    revised = chat(system=system, user=prompt, max_tokens=4000)

    # Create new version
    new_version = Script(
        project_id=script.project_id,
        idea_id=script.idea_id,
        version=script.version + 1.0,
        is_active=True,
        title=script.title,
        hook=script.hook,
        full_script=revised,
        segment_outline=script.segment_outline,
        cta=script.cta,
        pacing_notes=script.pacing_notes,
        trend_match_score=script.trend_match_score,
        trend_match_explanation=script.trend_match_explanation,
        brain_prediction=script.brain_prediction,
    )
    db.query(Script).filter(Script.project_id == script.project_id).update({"is_active": False})
    db.add(new_version)
    db.commit()
    db.refresh(new_version)
    return new_version
