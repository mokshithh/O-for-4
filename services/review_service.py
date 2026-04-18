"""
Review Service
==============
Orchestrates the full video review pipeline:
  1. Video ingest (upload or YT)
  2. Transcript extraction + segmentation
  3. TRIBE v2 brain analysis
  4. Claude coaching and score generation
  5. Script divergence detection
  6. Persistence
"""

from __future__ import annotations
import json
import logging
from typing import Optional
from sqlalchemy.orm import Session

from models.project import Project, ProjectStatus
from models.review import VideoReview, ReviewSegment, VideoSource, ReviewStatus, PerformanceLabel
from models.script import Script
from brain.service import get_brain_service, BrainAnalysisResult
from services import transcript_service, video_service
from services.claude_client import chat

logger = logging.getLogger(__name__)


def _score_to_label(score: float) -> PerformanceLabel:
    if score >= 80:
        return PerformanceLabel.high_potential
    elif score >= 65:
        return PerformanceLabel.strong
    elif score >= 45:
        return PerformanceLabel.promising
    else:
        return PerformanceLabel.weak


def _generate_claude_review(
    transcript: str,
    project: Project,
    brain_result,
    script: Optional[Script],
) -> dict:
    """Use Claude to generate coaching feedback, score explanations, and suggestions."""
    system = (
        "You are a blunt, smart YouTube creator coach. You give direct, useful feedback. "
        "You never over-praise weak content. You sound like a strategist who has studied what "
        "makes long-form YouTube videos retain audiences and go viral. "
        "Output must be valid JSON only — no markdown fences, no extra commentary."
    )

    weak_segments = [
        f"- {seg.label} (attention: {seg.attention_continuity:.0%}): {seg.weakness_reason or 'Attention drops'}"
        for seg in brain_result.segments if seg.is_weak
    ] if brain_result else []

    script_context = ""
    if script:
        script_context = f"\nOriginal script title: {script.title or 'N/A'}"

    prompt = f"""
Creator profile:
- Niche: {project.niche}
- Tone: {project.tone}
- Target audience: {project.target_audience}
- Goal: {project.goal}
{script_context}

Video transcript (may be partial):
{transcript[:3000] if transcript else "Transcript unavailable — analyse based on structure signals."}

Brain analysis signals:
- Overall attention mean: {brain_result.tribe_raw.get('overall_attention_mean', 'N/A') if brain_result and brain_result.tribe_raw else 'N/A'}
- Weak segments: {chr(10).join(weak_segments) if weak_segments else 'None identified'}

Generate a complete review. Return a JSON object with this structure:
{{
  "niche_fit_score": <float 0-100>,
  "retention_potential_score": <float 0-100>,
  "brain_engagement_score": <float 0-100>,
  "virality_potential_score": <float 0-100>,
  "coaching_feedback": "3-5 sentences of blunt, direct coaching. No fluff.",
  "score_explanations": {{
    "niche_fit": {{"score": <float>, "reasoning": "...", "dataset_signal": "..."}},
    "retention_potential": {{"score": <float>, "reasoning": "...", "dataset_signal": "..."}},
    "brain_engagement": {{"score": <float>, "reasoning": "...", "dataset_signal": "..."}},
    "virality_potential": {{"score": <float>, "reasoning": "...", "dataset_signal": "..."}}
  }},
  "improvement_suggestions": ["specific suggestion 1", "specific suggestion 2", "..."]
}}

Tone requirements:
- Coaching feedback should sound like: 'The intro takes too long to get to the point.' NOT 'Great video!'
- Improvement suggestions must be specific and actionable — not generic tips
- Be honest about low scores — do not inflate
- Return ONLY the JSON object
"""

    raw = chat(system=system, user=prompt, max_tokens=2000)

    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as exc:
        logger.error("Claude review JSON parse failed: %s", exc)
        return {
            "niche_fit_score": 50.0,
            "retention_potential_score": 50.0,
            "brain_engagement_score": 50.0,
            "virality_potential_score": 50.0,
            "coaching_feedback": "Review analysis encountered an error. Please retry.",
            "score_explanations": {},
            "improvement_suggestions": ["Retry the review for detailed suggestions."],
        }


def _check_script_divergence(transcript: str, script: Script) -> tuple[bool, Optional[str]]:
    """Detect if the video diverged meaningfully from the generated script."""
    if not transcript or not script:
        return False, None

    system = (
        "You compare a YouTube script to an actual video transcript. "
        "Return JSON only: {\"diverged\": bool, \"notes\": \"explanation or null\"}"
    )
    prompt = f"""
Script title: {script.title}
Script hook: {script.hook or 'N/A'}

Transcript start (first 1000 chars): {transcript[:1000]}

Did the creator significantly diverge from the planned script?
Consider: different topic, dropped key sections, completely different angle.
Minor improvisation is NOT divergence.
"""
    try:
        raw = chat(system=system, user=prompt, max_tokens=300)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        return data.get("diverged", False), data.get("notes")
    except Exception:
        return False, None


async def process_review(review: VideoReview, video_path: str, db: Session) -> VideoReview:
    """
    Full async review pipeline. Called after video is saved to temp storage.
    Updates review record in place.
    """
    try:
        review.status = ReviewStatus.processing
        db.commit()

        project = db.query(Project).filter(Project.id == review.project_id).first()
        script = None
        if review.script_id:
            script = db.query(Script).filter(Script.id == review.script_id).first()

        # 1. Get video duration
        duration = video_service.get_video_duration(video_path)
        review.duration_seconds = duration

        # 2. Extract transcript
        transcript_segments = transcript_service.extract_segments_from_whisper(video_path)
        if not transcript_segments and duration:
            transcript_segments = transcript_service.build_mock_segments(duration)

        full_transcript = " ".join(s["text"] for s in transcript_segments)
        review.transcript = full_transcript[:50000]  # Cap storage size

        # 3. TRIBE v2 brain analysis
        brain_svc = get_brain_service()
        num_segments = max(len(transcript_segments), 5)
        tribe_output = brain_svc.run_tribe_inference(video_path, num_segments)
        segment_analyses = brain_svc.translate_tribe_to_segments(tribe_output, transcript_segments)

        tribe_raw = {
            "overall_attention_mean": tribe_output.overall_attention_mean,
            "overall_attention_std": tribe_output.overall_attention_std,
            "low_attention_timestamps": tribe_output.low_attention_timestamps,
            "model_version": tribe_output.model_version,
        }

        # 4. Claude coaching analysis
        class _FakeBrainResult:
            segments = segment_analyses
            tribe_raw = tribe_raw

        claude_data = _generate_claude_review(
            transcript=full_transcript,
            project=project,
            brain_result=_FakeBrainResult(),
            script=script,
        )

        # 5. Compute overall score
        scores = [
            claude_data.get("niche_fit_score", 50),
            claude_data.get("retention_potential_score", 50),
            claude_data.get("brain_engagement_score", 50),
            claude_data.get("virality_potential_score", 50),
        ]
        overall = round(sum(scores) / len(scores), 1)

        # 6. Script divergence check
        diverged, div_notes = False, None
        if script and full_transcript:
            diverged, div_notes = _check_script_divergence(full_transcript, script)

        # 7. Persist all scores and segments
        review.overall_score = overall
        review.niche_fit_score = claude_data.get("niche_fit_score")
        review.retention_potential_score = claude_data.get("retention_potential_score")
        review.brain_engagement_score = claude_data.get("brain_engagement_score")
        review.virality_potential_score = claude_data.get("virality_potential_score")
        review.performance_label = _score_to_label(overall)
        review.coaching_feedback = claude_data.get("coaching_feedback")
        review.score_explanations = claude_data.get("score_explanations")
        review.improvement_suggestions = claude_data.get("improvement_suggestions")
        review.script_divergence_flagged = diverged
        review.script_divergence_notes = div_notes
        review.tribe_raw_output = tribe_raw
        review.tribe_used = brain_svc.is_tribe_active()
        review.status = ReviewStatus.complete

        # 8. Persist segments
        for seg in segment_analyses:
            db_seg = ReviewSegment(
                review_id=review.id,
                segment_index=seg.segment_index,
                label=seg.label,
                start_seconds=seg.start_seconds,
                end_seconds=seg.end_seconds,
                transcript_excerpt=seg.transcript_excerpt,
                engagement_score=seg.engagement_score,
                retention_risk=seg.retention_risk,
                is_weak=seg.is_weak,
                weakness_reason=seg.weakness_reason,
                coaching_note=seg.coaching_note,
                attention_continuity=seg.attention_continuity,
            )
            db.add(db_seg)

        project.status = ProjectStatus.review_complete
        db.commit()
        db.refresh(review)

    except Exception as exc:
        logger.error("Review processing failed: %s", exc, exc_info=True)
        review.status = ReviewStatus.failed
        review.error_message = str(exc)
        db.commit()

    finally:
        # Always clean up temp file
        try:
            video_service.delete_temp_file(video_path)
        except Exception:
            pass

    return review
