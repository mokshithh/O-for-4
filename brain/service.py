"""
Brain Analysis Service
======================
Single entry point for the video brain review pipeline.

Orchestrates:
  1. TRIBE v2 adapter (real or mock)
  2. Claude-based transcript analysis
  3. Segment-level scoring
  4. Product-facing signal translation
"""

from __future__ import annotations
import logging
from typing import Optional
from dataclasses import dataclass, field

from core.config import settings
from brain.tribe_adapter import TribeV2Adapter, TribeVideoOutput
from brain.mock_brain import generate_mock_tribe_output

logger = logging.getLogger(__name__)


@dataclass
class SegmentAnalysis:
    segment_index: int
    label: str
    start_seconds: float
    end_seconds: float
    transcript_excerpt: str
    engagement_score: float
    retention_risk: float
    is_weak: bool
    weakness_reason: Optional[str]
    coaching_note: Optional[str]
    attention_continuity: float


@dataclass
class BrainAnalysisResult:
    overall_score: float
    niche_fit_score: float
    retention_potential_score: float
    brain_engagement_score: float
    virality_potential_score: float
    performance_label: str
    coaching_feedback: str
    score_explanations: dict
    improvement_suggestions: list[str]
    segments: list[SegmentAnalysis]
    tribe_used: bool
    tribe_raw: Optional[dict] = None

    # Script divergence
    script_divergence_flagged: bool = False
    script_divergence_notes: Optional[str] = None


class BrainAnalysisService:
    """
    Orchestrates TRIBE v2 + Claude analysis for a submitted video.

    Design contract:
      - Always returns a BrainAnalysisResult regardless of whether TRIBE model is available.
      - TRIBE unavailability degrades gracefully to mock output.
      - Claude handles transcript-level reasoning and product-facing copy.
    """

    def __init__(self):
        self._tribe: Optional[TribeV2Adapter] = None
        self._tribe_active = False

        if settings.tribe_enabled:
            self._tribe = TribeV2Adapter(settings.tribe_model_path)
            self._tribe_active = self._tribe.load()
            if self._tribe_active:
                logger.info("TRIBE v2 model loaded successfully.")
            else:
                logger.warning("TRIBE v2 load failed — using mock path.")

    def is_tribe_active(self) -> bool:
        return self._tribe_active

    def run_tribe_inference(self, video_path: str, num_segments: int) -> TribeVideoOutput:
        """Run TRIBE v2 or fall back to mock."""
        if self._tribe_active and self._tribe:
            result = self._tribe.analyze(video_path)
            if result:
                return result
            logger.warning("TRIBE inference returned None — using mock.")

        return generate_mock_tribe_output(
            num_segments=num_segments,
            seed=hash(video_path) % 10000,
        )

    def translate_tribe_to_segments(
        self,
        tribe_output: TribeVideoOutput,
        transcript_segments: list[dict],
    ) -> list[SegmentAnalysis]:
        """Map TribeVideoOutput + transcript segments → SegmentAnalysis list."""
        results = []
        segment_labels = [
            "Hook", "Act 1", "Act 2", "Act 3", "Build", "Climax",
            "Resolution", "CTA", "Outro"
        ]

        for i, signal in enumerate(tribe_output.segment_signals):
            label = segment_labels[i] if i < len(segment_labels) else f"Segment {i + 1}"
            excerpt = ""
            if i < len(transcript_segments):
                excerpt = transcript_segments[i].get("text", "")[:300]

            retention_risk = max(0.0, 1.0 - signal.attention_continuity)
            engagement = round(signal.attention_continuity * 100, 1)
            is_weak = signal.attention_continuity < 0.6

            coaching_note = None
            weakness_reason = None
            if is_weak:
                weakness_reason = "Attention continuity drops below threshold in this segment."
                coaching_note = "Consider tightening the pacing or adding a pattern interrupt here."

            results.append(SegmentAnalysis(
                segment_index=i,
                label=label,
                start_seconds=signal.start_seconds,
                end_seconds=signal.end_seconds,
                transcript_excerpt=excerpt,
                engagement_score=engagement,
                retention_risk=round(retention_risk, 3),
                is_weak=is_weak,
                weakness_reason=weakness_reason,
                coaching_note=coaching_note,
                attention_continuity=signal.attention_continuity,
            ))

        return results


_brain_service: Optional[BrainAnalysisService] = None


def get_brain_service() -> BrainAnalysisService:
    global _brain_service
    if _brain_service is None:
        _brain_service = BrainAnalysisService()
    return _brain_service
