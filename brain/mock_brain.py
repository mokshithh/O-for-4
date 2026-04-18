"""
Mock brain analysis — used when TRIBE_ENABLED=false or model unavailable.
Generates plausible-looking outputs from transcript/metadata analysis via Claude.
"""

from __future__ import annotations
import random
from typing import Optional
from brain.tribe_adapter import TribeVideoOutput, TribeSegmentSignal


def generate_mock_tribe_output(
    num_segments: int,
    segment_duration: float = 30.0,
    seed: Optional[int] = None,
) -> TribeVideoOutput:
    """
    Produce a mock TribeVideoOutput that mimics real model structure.
    Used as fallback when TRIBE model is unavailable.
    """
    rng = random.Random(seed)

    signals = []
    for i in range(num_segments):
        # Simulate typical attention curve: high at start, dip in middle, recovery
        base = 0.75
        if i == 0:
            base = 0.85
        elif i == num_segments // 2:
            base = 0.55
        elif i == num_segments - 1:
            base = 0.65

        attention = max(0.1, min(1.0, base + rng.gauss(0, 0.08)))
        signals.append(
            TribeSegmentSignal(
                segment_index=i,
                start_seconds=i * segment_duration,
                end_seconds=(i + 1) * segment_duration,
                attention_continuity=round(attention, 3),
                engagement_logit=round(attention * 2 - 1, 3),
            )
        )

    attention_values = [s.attention_continuity for s in signals]
    mean_attention = sum(attention_values) / len(attention_values) if attention_values else 0.5

    low_attention = [
        s.start_seconds for s in signals if s.attention_continuity < 0.6
    ]

    return TribeVideoOutput(
        segment_signals=signals,
        overall_attention_mean=round(mean_attention, 3),
        overall_attention_std=round((sum((v - mean_attention) ** 2 for v in attention_values) / len(attention_values)) ** 0.5, 3),
        low_attention_timestamps=low_attention,
        model_version="mock_v1",
    )
