"""
Review Service
==============
Orchestrates the full video review pipeline:
  1. Video ingest (upload or YT)
  2. Transcript extraction + segmentation (Whisper / fallback)
  3. TRIBE v2 brain analysis (real model or Claude-powered brain simulation)
  4. Claude coaching and score generation
  5. Script divergence detection
  6. Persistence

Brain simulation (active fallback when TRIBE v2 model unavailable):
  Uses Claude to analyse the transcript segment-by-segment and predict
  attention continuity scores that mimic fMRI-derived engagement curves.
  This is NOT random — it analyses hook quality, pacing, topic novelty,
  and structural signals to produce meaningful per-segment predictions.
"""

from __future__ import annotations
import json
import logging
from typing import Optional
from sqlalchemy.orm import Session

from models.project import Project, ProjectStatus
from models.review import VideoReview, ReviewSegment, VideoSource, ReviewStatus, PerformanceLabel
from models.script import Script
from brain.service import get_brain_service
from services import transcript_service, video_service
from services.claude_client import chat

logger = logging.getLogger(__name__)


# ── Brain simulation ────────────────────────────────────────────────────────

def _simulate_brain_engagement(
    transcript_segments: list[dict],
    project: Project,
    script: Optional[Script] = None,
) -> list[dict]:
    """
    Claude-powered brain engagement simulation.

    Analyses each transcript segment for signals that predict fMRI-style
    attention continuity: hook quality, information density, novelty,
    pacing, emotional resonance, and structural clarity.

    Returns a list of segment dicts enriched with:
      - attention_continuity (0–1)
      - engagement_score (0–100)
      - retention_risk (0–1)
      - is_weak (bool)
      - weakness_reason (str or None)
      - coaching_note (str or None)
    """
    if not transcript_segments:
        return []

    system = (
        "You are a neuroscience-informed YouTube engagement analyst. "
        "You simulate how a viewer's brain responds to video content second-by-second. "
        "You assess attention continuity based on hook strength, information novelty, "
        "pacing, emotional resonance, and structural clarity. "
        "Output must be valid JSON only — no markdown fences, no commentary."
    )

    segments_summary = "\n".join([
        f"Segment {i+1} ({s.get('start', 0):.0f}s–{s.get('end', 0):.0f}s): {s.get('text', '')[:200]}"
        for i, s in enumerate(transcript_segments[:12])
    ])

    script_context = f"\nScript title: {script.title}" if script else ""

    prompt = f"""
Creator profile:
- Niche: {project.niche}
- Target audience: {project.target_audience}
- Tone: {project.tone}
- Goal: {project.goal}{script_context}

Video transcript segments:
{segments_summary}

For each segment, simulate a brain engagement score as if you were predicting fMRI cortical activity.
High score = high neural engagement (novel info, tension, strong hook, clear value).
Low score = attention drift (slow pacing, repetition, off-topic, weak delivery).

Return a JSON array with one entry per segment, in order:
[
  {{
    "segment_index": 0,
    "attention_continuity": <float 0.0–1.0>,
    "label": "<segment label e.g. Hook / Act 1 / Climax / CTA>",
    "is_weak": <bool>,
    "weakness_reason": "<specific reason or null>",
    "coaching_note": "<actionable note or null>"
  }},
  ...
]

Rules:
- Segment 0 (hook) should be scored relative to how quickly it creates tension or curiosity
- Middle segments should reflect pacing — flag repetition, tangents, slow build as weak
- Final segment (CTA) should reflect clarity and conviction
- At least 1 segment should be flagged weak unless the content is genuinely exceptional
- Be specific in weakness_reason — reference what's in the transcript
- Return ONLY the JSON array
"""

    try:
        raw = chat(system=system, user=prompt, max_tokens=1500)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        scored = json.loads(raw)
    except Exception as exc:
        logger.warning("Brain simulation Claude call failed: %s — using fallback curve", exc)
        scored = _fallback_engagement_curve(len(transcript_segments))

    # Merge scores back with original segment timing
    results = []
    for i, seg in enumerate(transcript_segments):
        scored_seg = scored[i] if i < len(scored) else {}
        attention = float(scored_seg.get("attention_continuity", 0.65))
        attention = max(0.1, min(1.0, attention))

        results.append({
            "segment_index": i,
            "label": scored_seg.get("label", f"Segment {i+1}"),
            "start_seconds": seg.get("start", i * 30.0),
            "end_seconds": seg.get("end", (i + 1) * 30.0),
            "transcript_excerpt": seg.get("text", "")[:300],
            "attention_continuity": attention,
            "engagement_score": round(attention * 100, 1),
            "retention_risk": round(1.0 - attention, 3),
            "is_weak": bool(scored_seg.get("is_weak", attention < 0.6)),
            "weakness_reason": scored_seg.get("weakness_reason"),
            "coaching_note": scored_seg.get("coaching_note"),
        })

    return results


def _fallback_engagement_curve(n: int) -> list[dict]:
    """Structural attention curve when Claude call fails."""
    import math
    labels = ["Hook", "Act 1", "Act 2", "Build", "Climax", "Resolution", "CTA", "Outro"]
    result = []
    for i in range(n):
        t = i / max(n - 1, 1)
        # Typical YouTube curve: high start, mid-video dip, recovery
        attention = 0.82 - 0.25 * math.sin(math.pi * t) + 0.05 * (1 - t)
        attention = max(0.35, min(0.92, attention))
        is_weak = attention < 0.6
        result.append({
            "segment_index": i,
            "attention_continuity": round(attention, 3),
            "label": labels[i] if i < len(labels) else f"Segment {i+1}",
            "is_weak": is_weak,
            "weakness_reason": "Attention continuity drops in this section." if is_weak else None,
            "coaching_note": "Consider tightening pacing or adding a pattern interrupt here." if is_weak else None,
        })
    return result


# ── Score label ─────────────────────────────────────────────────────────────

def _score_to_label(score: float) -> PerformanceLabel:
    if score >= 80:
        return PerformanceLabel.high_potential
    elif score >= 65:
        return PerformanceLabel.strong
    elif score >= 45:
        return PerformanceLabel.promising
    else:
        return PerformanceLabel.weak


# ── Claude coaching ─────────────────────────────────────────────────────────

def _generate_claude_review(
    transcript: str,
    project: Project,
    segment_analyses: list[dict],
    script: Optional[Script],
) -> dict:
    """Use Claude to generate coaching feedback, scores, and suggestions."""
    system = (
        "You are a blunt, smart YouTube creator coach. You give direct, useful feedback. "
        "You never over-praise weak content. You sound like a strategist who has studied what "
        "makes long-form YouTube videos retain audiences and go viral. "
        "Output must be valid JSON only — no markdown fences, no extra commentary."
    )

    weak_segments = [
        f"- {seg['label']} ({seg['attention_continuity']:.0%} attention): {seg['weakness_reason'] or 'Attention drops'}"
        for seg in segment_analyses if seg.get("is_weak")
    ]

    mean_attention = (
        sum(s["attention_continuity"] for s in segment_analyses) / len(segment_analyses)
        if segment_analyses else 0.5
    )

    script_context = f"\nOriginal script title: {script.title or 'N/A'}" if script else ""

    prompt = f"""
Creator profile:
- Niche: {project.niche}
- Tone: {project.tone}
- Target audience: {project.target_audience}
- Goal: {project.goal}{script_context}

Video transcript (may be partial):
{transcript[:3000] if transcript else "Transcript unavailable — analyse based on structure signals."}

Brain engagement analysis:
- Mean attention continuity: {mean_attention:.1%}
- Number of weak segments: {len(weak_segments)}
- Weak segments:
{chr(10).join(weak_segments) if weak_segments else '  None identified'}

Generate a complete video review. Return a JSON object:
{{
  "niche_fit_score": <float 0–100>,
  "retention_potential_score": <float 0–100>,
  "brain_engagement_score": <float 0–100>,
  "virality_potential_score": <float 0–100>,
  "coaching_feedback": "3–5 sentences of blunt, direct coaching. No fluff. Examples: 'The intro takes too long to get to the point.' / 'You lose momentum badly in the middle.'",
  "score_explanations": {{
    "niche_fit": {{"score": <float>, "reasoning": "2 sentences", "dataset_signal": "trend signal or N/A"}},
    "retention_potential": {{"score": <float>, "reasoning": "2 sentences", "dataset_signal": "trend signal or N/A"}},
    "brain_engagement": {{"score": <float>, "reasoning": "2 sentences referencing the attention data", "dataset_signal": "trend signal or N/A"}},
    "virality_potential": {{"score": <float>, "reasoning": "2 sentences", "dataset_signal": "trend signal or N/A"}}
  }},
  "improvement_suggestions": ["specific actionable suggestion 1", "specific actionable suggestion 2", "specific actionable suggestion 3"]
}}

Requirements:
- brain_engagement_score should be close to {mean_attention * 100:.0f} (based on brain simulation)
- Be honest — do not inflate scores
- Improvement suggestions must be specific to this video, not generic tips
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
        logger.error("Claude review parse failed: %s", exc)
        return {
            "niche_fit_score": 50.0,
            "retention_potential_score": 50.0,
            "brain_engagement_score": round(mean_attention * 100, 1),
            "virality_potential_score": 50.0,
            "coaching_feedback": "Review analysis encountered an error. Please retry.",
            "score_explanations": {},
            "improvement_suggestions": ["Retry the review for detailed suggestions."],
        }


# ── Script divergence ───────────────────────────────────────────────────────

def _check_script_divergence(transcript: str, script: Script) -> tuple[bool, Optional[str]]:
    system = (
        "Compare a YouTube script to an actual video transcript. "
        "Return JSON only: {\"diverged\": bool, \"notes\": \"explanation or null\"}"
    )
    prompt = f"""
Script title: {script.title}
Script hook: {script.hook or 'N/A'}
Transcript start: {transcript[:1000]}

Did the creator significantly diverge from the planned script?
Minor improvisation is NOT divergence. Only flag if topic/angle changed substantially.
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


# ── Main pipeline ───────────────────────────────────────────────────────────

async def process_review(review: VideoReview, video_path: str, db: Session) -> VideoReview:
    """Full async review pipeline. Updates review record in place."""
    try:
        review.status = ReviewStatus.processing
        db.commit()

        project = db.query(Project).filter(Project.id == review.project_id).first()
        script = None
        if review.script_id:
            script = db.query(Script).filter(Script.id == review.script_id).first()

        # 1. Video duration
        duration = video_service.get_video_duration(video_path)
        review.duration_seconds = duration

        # 2. Transcript extraction (Whisper or mock)
        transcript_segments = transcript_service.extract_segments_from_whisper(video_path)
        if not transcript_segments:
            fallback_duration = duration or 300.0
            transcript_segments = transcript_service.build_mock_segments(fallback_duration)

        full_transcript = " ".join(s.get("text", "") for s in transcript_segments)
        review.transcript = full_transcript[:50000]

        # 3. Brain simulation (TRIBE v2 or Claude-powered)
        brain_svc = get_brain_service()
        if brain_svc.is_tribe_active():
            # Real TRIBE v2 path
            tribe_output = brain_svc.run_tribe_inference(video_path, len(transcript_segments))
            segment_analyses = []
            labels = ["Hook", "Act 1", "Act 2", "Act 3", "Build", "Climax", "Resolution", "CTA", "Outro"]
            for i, signal in enumerate(tribe_output.segment_signals):
                ts = transcript_segments[i] if i < len(transcript_segments) else {}
                attention = signal.attention_continuity
                segment_analyses.append({
                    "segment_index": i,
                    "label": labels[i] if i < len(labels) else f"Segment {i+1}",
                    "start_seconds": signal.start_seconds,
                    "end_seconds": signal.end_seconds,
                    "transcript_excerpt": ts.get("text", "")[:300],
                    "attention_continuity": attention,
                    "engagement_score": round(attention * 100, 1),
                    "retention_risk": round(1.0 - attention, 3),
                    "is_weak": attention < 0.6,
                    "weakness_reason": "Attention continuity below threshold." if attention < 0.6 else None,
                    "coaching_note": "Consider adding a pattern interrupt here." if attention < 0.6 else None,
                })
            tribe_raw = {
                "overall_attention_mean": tribe_output.overall_attention_mean,
                "overall_attention_std": tribe_output.overall_attention_std,
                "low_attention_timestamps": tribe_output.low_attention_timestamps,
                "model_version": tribe_output.model_version,
            }
        else:
            # Claude-powered brain simulation
            segment_analyses = _simulate_brain_engagement(transcript_segments, project, script)
            mean_att = sum(s["attention_continuity"] for s in segment_analyses) / max(len(segment_analyses), 1)
            tribe_raw = {
                "overall_attention_mean": round(mean_att, 3),
                "overall_attention_std": 0.12,
                "low_attention_timestamps": [s["start_seconds"] for s in segment_analyses if s["is_weak"]],
                "model_version": "claude_brain_sim_v1",
            }

        # 4. Claude coaching
        claude_data = _generate_claude_review(
            transcript=full_transcript,
            project=project,
            segment_analyses=segment_analyses,
            script=script,
        )

        # 5. Overall score
        scores = [
            claude_data.get("niche_fit_score", 50),
            claude_data.get("retention_potential_score", 50),
            claude_data.get("brain_engagement_score", 50),
            claude_data.get("virality_potential_score", 50),
        ]
        overall = round(sum(scores) / len(scores), 1)

        # 6. Script divergence
        diverged, div_notes = False, None
        if script and full_transcript and "[Transcript unavailable" not in full_transcript:
            diverged, div_notes = _check_script_divergence(full_transcript, script)

        # 7. Persist review
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
                segment_index=seg["segment_index"],
                label=seg["label"],
                start_seconds=seg.get("start_seconds"),
                end_seconds=seg.get("end_seconds"),
                transcript_excerpt=seg.get("transcript_excerpt"),
                engagement_score=seg.get("engagement_score"),
                retention_risk=seg.get("retention_risk"),
                is_weak=seg.get("is_weak", False),
                weakness_reason=seg.get("weakness_reason"),
                coaching_note=seg.get("coaching_note"),
                attention_continuity=seg.get("attention_continuity"),
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
        try:
            video_service.delete_temp_file(video_path)
        except Exception:
            pass

    return review
