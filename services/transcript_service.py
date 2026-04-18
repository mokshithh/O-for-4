"""
Transcript and Segmentation Service
=====================================
Extracts transcript from video audio and splits into meaningful segments.
"""

from __future__ import annotations
import logging
import os
import tempfile
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_transcript(video_path: str) -> Optional[str]:
    """
    Extract transcript from video using OpenAI Whisper.
    Returns full transcript text or None on failure.
    """
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(video_path, fp16=False)
        return result.get("text", "")
    except Exception as exc:
        logger.warning("Whisper transcription failed: %s", exc)
        return None


def extract_segments_from_whisper(video_path: str, segment_duration: float = 30.0) -> list[dict]:
    """
    Run Whisper with word-level timestamps and group into segments.
    Returns list of {text, start, end} dicts.
    """
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(video_path, fp16=False, verbose=False)

        raw_segments = result.get("segments", [])
        if not raw_segments:
            return []

        # Group whisper segments into ~segment_duration buckets
        grouped: list[dict] = []
        current_bucket: dict = {"text": "", "start": None, "end": None}

        for seg in raw_segments:
            if current_bucket["start"] is None:
                current_bucket["start"] = seg["start"]

            current_bucket["text"] += " " + seg["text"]
            current_bucket["end"] = seg["end"]

            if (seg["end"] - current_bucket["start"]) >= segment_duration:
                grouped.append({
                    "text": current_bucket["text"].strip(),
                    "start": current_bucket["start"],
                    "end": current_bucket["end"],
                })
                current_bucket = {"text": "", "start": None, "end": None}

        # Flush remaining
        if current_bucket["text"].strip():
            grouped.append({
                "text": current_bucket["text"].strip(),
                "start": current_bucket["start"],
                "end": current_bucket["end"],
            })

        return grouped

    except Exception as exc:
        logger.warning("Segment extraction failed: %s", exc)
        return []


def build_mock_segments(duration_seconds: float, segment_duration: float = 30.0) -> list[dict]:
    """
    Build placeholder segments when Whisper is unavailable.
    Used for testing and graceful degradation.
    """
    segments = []
    t = 0.0
    i = 0
    while t < duration_seconds:
        end = min(t + segment_duration, duration_seconds)
        segments.append({
            "text": f"[Transcript unavailable for segment {i + 1}]",
            "start": t,
            "end": end,
        })
        t = end
        i += 1
    return segments
