"""
Transcript Service — OpenAI cloud Whisper API.

Uses OpenAI whisper-1 for transcription (no local torch dependency).
Falls back to mock segments when transcription is unavailable.
"""

from __future__ import annotations
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from core.config import settings

logger = logging.getLogger(__name__)


def _find_ffmpeg() -> str:
    """Auto-detect ffmpeg: config override → imageio-ffmpeg bundle → PATH."""
    if settings.ffmpeg_path and os.path.exists(settings.ffmpeg_path):
        return settings.ffmpeg_path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    return "ffmpeg"  # fall back to PATH


FFMPEG = _find_ffmpeg()


def _extract_audio(video_path: str) -> Optional[str]:
    """Extract audio track from video to a temp MP3 file using ffmpeg."""
    try:
        if not os.path.exists(FFMPEG):
            logger.warning("ffmpeg not found at %s", FFMPEG)
            return None
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        result = subprocess.run(
            [FFMPEG, "-y", "-i", video_path, "-vn", "-ar", "16000", "-ac", "1",
             "-ab", "64k", "-f", "mp3", tmp.name],
            capture_output=True, timeout=120,
        )
        if result.returncode != 0:
            logger.warning("ffmpeg audio extraction failed: %s", result.stderr.decode()[:300])
            os.unlink(tmp.name)
            return None
        return tmp.name
    except Exception as exc:
        logger.warning("Audio extraction error: %s", exc)
        return None


def _chunk_audio_if_needed(audio_path: str, max_mb: float = 24.0) -> list[str]:
    """If audio > 24 MB, split into chunks. Returns list of file paths."""
    size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    if size_mb <= max_mb:
        return [audio_path]

    # Estimate duration via ffprobe-free approach: chunk by time
    # Each chunk = 10 minutes
    chunk_duration = 600
    chunks = []
    i = 0
    start = 0

    while True:
        out = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        out.close()
        result = subprocess.run(
            [FFMPEG, "-y", "-i", audio_path, "-ss", str(start),
             "-t", str(chunk_duration), "-c", "copy", out.name],
            capture_output=True, timeout=60,
        )
        # Stop if output is empty (past end of file)
        if result.returncode != 0 or os.path.getsize(out.name) < 1000:
            os.unlink(out.name)
            break
        chunks.append(out.name)
        start += chunk_duration
        i += 1
        if i > 20:  # safety cap
            break

    return chunks if chunks else [audio_path]


def _get_video_duration_ffmpeg(video_path: str) -> Optional[float]:
    """Get video duration in seconds using ffmpeg."""
    try:
        if not os.path.exists(FFMPEG):
            return None
        result = subprocess.run(
            [FFMPEG, "-i", video_path],
            capture_output=True, timeout=15,
        )
        # Duration appears in stderr
        stderr = result.stderr.decode(errors="ignore")
        for line in stderr.splitlines():
            if "Duration:" in line:
                dur_str = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = dur_str.split(":")
                return float(h) * 3600 + float(m) * 60 + float(s)
    except Exception as exc:
        logger.warning("Duration extraction failed: %s", exc)
    return None


def _transcribe_with_openai(audio_path: str) -> Optional[list[dict]]:
    """Send audio file to OpenAI whisper-1 API, return segments."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        with open(audio_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
        raw_segs = getattr(response, "segments", None) or []
        result = []
        for s in raw_segs:
            # OpenAI SDK returns TranscriptionSegment objects (attribute access)
            text = getattr(s, "text", None) or s.get("text", "") if hasattr(s, "get") else getattr(s, "text", "")
            start = getattr(s, "start", None) if not hasattr(s, "get") else s.get("start", 0)
            end = getattr(s, "end", None) if not hasattr(s, "get") else s.get("end", 0)
            if text and str(text).strip():
                result.append({"text": str(text).strip(), "start": float(start), "end": float(end)})
        return result
    except Exception as exc:
        logger.warning("OpenAI Whisper API failed: %s", exc)
        return None


def extract_segments_from_whisper(video_path: str, segment_duration: float = 30.0) -> list[dict]:
    """
    Transcribe video using OpenAI cloud Whisper API + ffmpeg audio extraction.
    Groups raw segments into ~segment_duration buckets.
    Returns list of {text, start, end} dicts, or [] on failure.
    """
    # Step 1: Extract audio
    audio_path = _extract_audio(video_path)
    if not audio_path:
        logger.warning("Could not extract audio — using mock segments")
        return []

    try:
        # Step 2: Handle large files
        chunks = _chunk_audio_if_needed(audio_path)
        raw_segments: list[dict] = []
        time_offset = 0.0

        for chunk_path in chunks:
            segs = _transcribe_with_openai(chunk_path)
            if segs:
                # Apply time offset for chunked files
                for s in segs:
                    raw_segments.append({
                        "text": s["text"],
                        "start": s["start"] + time_offset,
                        "end": s["end"] + time_offset,
                    })
                if segs:
                    time_offset = segs[-1]["end"] + time_offset
            if chunk_path != audio_path:
                try:
                    os.unlink(chunk_path)
                except Exception:
                    pass

        if not raw_segments:
            return []

        # Step 3: Bucket into ~segment_duration groups
        grouped: list[dict] = []
        bucket = {"text": "", "start": None, "end": None}

        for seg in raw_segments:
            if bucket["start"] is None:
                bucket["start"] = seg["start"]
            bucket["text"] += " " + seg["text"]
            bucket["end"] = seg["end"]

            if (seg["end"] - bucket["start"]) >= segment_duration:
                grouped.append({
                    "text": bucket["text"].strip(),
                    "start": bucket["start"],
                    "end": bucket["end"],
                })
                bucket = {"text": "", "start": None, "end": None}

        if bucket["text"].strip():
            grouped.append({
                "text": bucket["text"].strip(),
                "start": bucket["start"],
                "end": bucket["end"],
            })

        return grouped

    finally:
        try:
            os.unlink(audio_path)
        except Exception:
            pass


def extract_transcript(video_path: str) -> Optional[str]:
    """Return full transcript text, or None on failure."""
    segs = extract_segments_from_whisper(video_path)
    return " ".join(s["text"] for s in segs) if segs else None


def get_video_duration(video_path: str) -> Optional[float]:
    """Return video duration in seconds."""
    return _get_video_duration_ffmpeg(video_path)


def build_mock_segments(duration_seconds: float, segment_duration: float = 30.0) -> list[dict]:
    """Placeholder segments when transcription is unavailable."""
    segments = []
    t = 0.0
    i = 0
    labels = ["Hook", "Introduction", "Act 1", "Act 2", "Build", "Climax", "Resolution", "CTA"]
    while t < duration_seconds:
        end = min(t + segment_duration, duration_seconds)
        label = labels[i] if i < len(labels) else f"Segment {i+1}"
        segments.append({
            "text": f"[Transcript unavailable — {label} ~{int(t)}s–{int(end)}s]",
            "start": t,
            "end": end,
        })
        t = end
        i += 1
    return segments
