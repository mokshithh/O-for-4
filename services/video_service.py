"""
Video Ingestion Service
========================
Handles file uploads and YouTube link fetching.
Raw videos are treated as temporary — not permanently stored.
"""

from __future__ import annotations
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from core.config import settings

logger = logging.getLogger(__name__)

TEMP_DIR = Path(settings.temp_upload_dir)
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def save_upload(file_bytes: bytes, original_filename: str) -> str:
    """Save uploaded bytes to a temp file. Returns temp file path."""
    suffix = Path(original_filename).suffix or ".mp4"
    temp_path = TEMP_DIR / f"{uuid.uuid4()}{suffix}"
    temp_path.write_bytes(file_bytes)
    logger.info("Saved upload to %s (%d bytes)", temp_path, len(file_bytes))
    return str(temp_path)


def fetch_youtube(youtube_url: str) -> str:
    """
    Download a YouTube video to a temp file using yt-dlp.
    Returns temp file path.
    """
    import yt_dlp

    temp_path = TEMP_DIR / f"{uuid.uuid4()}.mp4"
    ydl_opts = {
        "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
        "outtmpl": str(temp_path),
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])

    if not temp_path.exists():
        # yt-dlp may append extension
        candidates = list(TEMP_DIR.glob(f"{temp_path.stem}.*"))
        if candidates:
            temp_path = candidates[0]
        else:
            raise FileNotFoundError("yt-dlp did not produce output file")

    logger.info("Downloaded YouTube video to %s", temp_path)
    return str(temp_path)


def get_video_duration(video_path: str) -> Optional[float]:
    """Return video duration in seconds using ffmpeg (CapCut build)."""
    from services.transcript_service import get_video_duration as _dur
    return _dur(video_path)


def delete_temp_file(path: str) -> None:
    """Delete a temporary video file after processing."""
    try:
        os.remove(path)
        logger.info("Deleted temp file: %s", path)
    except Exception as exc:
        logger.warning("Could not delete temp file %s: %s", path, exc)
