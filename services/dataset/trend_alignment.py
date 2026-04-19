"""
TrendAlignmentService — produces structured dataset signals for idea generation,
script generation, and review explanation support.

Combines:
  - PatternClassifier (deterministic rules, always active)
  - DatasetLoader (CSV-backed stats, activates when CSV is present)
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Heuristic weights from spec §8
IDEA_RANK_WEIGHTS = {
    "trend_score": 0.40,
    "engagement_score": 0.25,
    "channel_fit": 0.15,
    "format_confidence": 0.10,
    "novelty_score": 0.10,
}

# Known high-performing patterns per rough niche bucket (fallback when CSV absent)
_PATTERN_HEURISTICS: dict[str, dict] = {
    "problem_truth":       {"base_engagement": 0.72, "base_reach": 0.65},
    "challenge_experiment":{"base_engagement": 0.70, "base_reach": 0.68},
    "question_curiosity":  {"base_engagement": 0.68, "base_reach": 0.55},
    "reveal_result":       {"base_engagement": 0.62, "base_reach": 0.60},
    "number_list":         {"base_engagement": 0.60, "base_reach": 0.70},
    "hype_announcement":   {"base_engagement": 0.55, "base_reach": 0.75},
    "generic_descriptive": {"base_engagement": 0.40, "base_reach": 0.40},
}

_FORMAT_HEURISTICS: dict[str, float] = {
    "explainer":   0.72,
    "story":       0.70,
    "commentary":  0.65,
    "review":      0.60,
    "challenge":   0.68,
    "reaction":    0.55,
    "announcement":0.50,
    "other":       0.45,
}

_HUMAN_PATTERN_NAMES = {
    "question_curiosity":   "curiosity-gap question",
    "hype_announcement":    "hype/announcement",
    "number_list":          "numbered list",
    "problem_truth":        "problem/truth framing",
    "challenge_experiment": "challenge/experiment",
    "reveal_result":        "reveal/result",
    "generic_descriptive":  "descriptive",
}


class TrendAlignmentService:

    def __init__(self):
        from services.dataset.pattern_classifier import get_classifier
        from services.dataset.loader import get_dataset_loader
        self._clf = get_classifier()
        self._loader = get_dataset_loader()

    # ── Public API ────────────────────────────────────────────────────────

    def get_idea_signals(self, niche: str, goal: str) -> dict:
        """
        Returns dataset intelligence to inject into the idea-generation prompt.
        Structure is stable regardless of whether CSV is loaded.
        """
        stats = self._loader.get_niche_stats(niche)
        csv_loaded = self._loader.is_loaded()

        if csv_loaded and stats.row_count >= 50:
            top_patterns = stats.top_patterns[:3]
            top_formats = stats.top_formats[:3]
            median_eng = stats.median_engagement
            p75_eng = stats.p75_engagement
            p90_eng = stats.p90_engagement
            avg_title_len = stats.avg_title_length
            source = "dataset"
        else:
            top_patterns = self._heuristic_top_patterns(niche, goal)
            top_formats = self._heuristic_top_formats(goal)
            median_eng = 0.04
            p75_eng = 0.09
            p90_eng = 0.16
            avg_title_len = 58.0
            source = "heuristic"

        pattern_labels = [_HUMAN_PATTERN_NAMES.get(p, p) for p in top_patterns]
        format_labels = [f.replace("_", " ") for f in top_formats]

        explanation = self._build_idea_explanation(
            niche, top_patterns, top_formats, median_eng, p75_eng, avg_title_len, source
        )

        return {
            "source": source,
            "niche": niche,
            "top_title_patterns": top_patterns,
            "top_title_pattern_labels": pattern_labels,
            "top_content_formats": top_formats,
            "top_content_format_labels": format_labels,
            "median_engagement_rate": round(median_eng, 4),
            "p75_engagement_rate": round(p75_eng, 4),
            "p90_engagement_rate": round(p90_eng, 4),
            "avg_title_length": round(avg_title_len, 1),
            "explanation_for_prompt": explanation,
            "ranking_guidance": self._build_ranking_guidance(niche, goal, top_patterns, top_formats),
        }

    def get_script_signals(self, niche: str, title: str, goal: str = "") -> dict:
        """
        Returns dataset intelligence to inject into the script-generation prompt.
        Classifies the proposed title and scores its alignment.
        """
        classification = self._clf.classify_all(title)
        pattern = classification["title_pattern"]
        fmt = classification["content_format"]
        hook = classification["hook_style"]

        stats = self._loader.get_niche_stats(niche)
        csv_loaded = self._loader.is_loaded() and stats.row_count >= 50

        # Pattern-level scores
        if csv_loaded and pattern in stats.pattern_stats:
            pstat = stats.pattern_stats[pattern]
            engagement_norm = min(pstat["avg_engagement"] / max(stats.p90_engagement, 0.001), 1.0)
            rank = stats.pattern_engagement_rank(pattern)
            saturation = stats.saturation_level(pattern)
            total_patterns = len(stats.pattern_stats)
        else:
            h = _PATTERN_HEURISTICS.get(pattern, {"base_engagement": 0.5, "base_reach": 0.5})
            engagement_norm = h["base_engagement"]
            rank = list(_PATTERN_HEURISTICS.keys()).index(pattern) + 1 if pattern in _PATTERN_HEURISTICS else 4
            saturation = "medium"
            total_patterns = len(_PATTERN_HEURISTICS)

        # Format score
        if csv_loaded and fmt in stats.format_stats:
            fstat = stats.format_stats[fmt]
            format_score = min(fstat["avg_engagement"] / max(stats.p90_engagement, 0.001), 1.0)
        else:
            format_score = _FORMAT_HEURISTICS.get(fmt, 0.5)

        # Composite scores (0-100)
        trend_score = round(min((engagement_norm * 0.6 + format_score * 0.4) * 110, 100), 1)
        novelty_score = round({"low": 80, "medium": 55, "high": 30, "unknown": 65}[saturation], 1)
        format_confidence = round(format_score * 100, 1)
        hook_strength = round(_PATTERN_HEURISTICS.get(pattern, {"base_engagement": 0.5})["base_engagement"] * 100, 1)

        title_len = len(title)
        if csv_loaded:
            title_len_note = (
                "optimal length" if 45 <= title_len <= 70
                else "shorter than typical high-performers" if title_len < 45
                else "longer than median — may still work"
            )
        else:
            title_len_note = "45–70 chars typically performs best"

        explanation = self._build_script_explanation(
            niche, pattern, fmt, hook, trend_score, novelty_score, saturation, rank, total_patterns
        )

        return {
            "source": "dataset" if csv_loaded else "heuristic",
            "classified_title_pattern": pattern,
            "classified_title_pattern_label": _HUMAN_PATTERN_NAMES.get(pattern, pattern),
            "classified_content_format": fmt,
            "classified_hook_style": hook.replace("_", " "),
            "trend_score": trend_score,
            "novelty_score": novelty_score,
            "format_confidence_score": format_confidence,
            "hook_strength_score": hook_strength,
            "saturation_level": saturation,
            "title_length_note": title_len_note,
            "pattern_rank_in_niche": rank,
            "explanation_for_prompt": explanation,
        }

    def get_review_benchmark(self, niche: str, title: str) -> dict:
        """Lightweight benchmark context for review score explanations."""
        signals = self.get_script_signals(niche, title)
        stats = self._loader.get_niche_stats(niche)
        csv_loaded = self._loader.is_loaded() and stats.row_count >= 50

        benchmark_text = (
            f"Comparable {niche} videos (dataset n={stats.row_count:,}): "
            f"median engagement {stats.median_engagement:.1%}, "
            f"top-quartile threshold {stats.p75_engagement:.1%}."
            if csv_loaded
            else f"Benchmark for {niche} niche: median engagement ~4%, top quartile ~9%."
        )

        return {
            "title_pattern": signals["classified_title_pattern_label"],
            "content_format": signals["classified_content_format"],
            "trend_score": signals["trend_score"],
            "novelty_score": signals["novelty_score"],
            "saturation_level": signals["saturation_level"],
            "benchmark_context": benchmark_text,
        }

    # ── Internal helpers ──────────────────────────────────────────────────

    def _heuristic_top_patterns(self, niche: str, goal: str) -> list[str]:
        niche_lower = niche.lower()
        goal_lower = goal.lower()
        if any(k in niche_lower for k in ["finance", "business", "entrepreneur"]):
            return ["problem_truth", "number_list", "reveal_result"]
        if any(k in goal_lower for k in ["viral", "reach", "subscribers"]):
            return ["challenge_experiment", "hype_announcement", "question_curiosity"]
        if any(k in niche_lower for k in ["education", "learning", "science"]):
            return ["explainer", "number_list", "question_curiosity"]
        return ["problem_truth", "challenge_experiment", "question_curiosity"]

    def _heuristic_top_formats(self, goal: str) -> list[str]:
        goal_lower = goal.lower()
        if "viral" in goal_lower or "community" in goal_lower:
            return ["story", "challenge", "commentary"]
        if "authority" in goal_lower or "educate" in goal_lower:
            return ["explainer", "review", "commentary"]
        return ["explainer", "story", "commentary"]

    def _build_idea_explanation(self, niche, top_patterns, top_formats, median_eng, p75_eng, avg_title_len, source) -> str:
        pattern_str = ", ".join(_HUMAN_PATTERN_NAMES.get(p, p) for p in top_patterns)
        format_str = ", ".join(f.replace("_", " ") for f in top_formats)
        src_note = f"YouTube trending dataset ({source})"
        return (
            f"Dataset intelligence for '{niche}' ({src_note}):\n"
            f"- Top performing title patterns: {pattern_str}\n"
            f"- Top content formats by engagement: {format_str}\n"
            f"- Median engagement rate: {median_eng:.1%} | Top-quartile threshold: {p75_eng:.1%}\n"
            f"- Optimal title length: 45–70 chars (dataset avg: {avg_title_len:.0f})\n"
            f"- Problem/truth framing and challenge/experiment formats punch above weight in most niches\n"
            f"- Longer, specific titles outperform vague short ones on engagement quality\n"
            f"Use these patterns to rank and frame the 5 ideas. Prioritise ideas whose angle fits the "
            f"top-performing patterns. The trend_alignment field should cite these signals specifically."
        )

    def _build_ranking_guidance(self, niche, goal, top_patterns, top_formats) -> str:
        pattern_str = ", ".join(top_patterns[:2])
        format_str = ", ".join(top_formats[:2])
        return (
            f"Rank ideas using: 40% trend alignment with {pattern_str} patterns, "
            f"25% engagement potential, 15% fit with '{goal}' goal, "
            f"10% format confidence ({format_str}), 10% novelty vs saturation. "
            f"Avoid generic titles — specific angle + strong pattern beats vague + broad."
        )

    def _build_script_explanation(self, niche, pattern, fmt, hook, trend_score, novelty_score, saturation, rank, total) -> str:
        pattern_label = _HUMAN_PATTERN_NAMES.get(pattern, pattern)
        return (
            f"Dataset intelligence for script generation:\n"
            f"- Detected title pattern: '{pattern_label}' — ranks #{rank} of {total} patterns by engagement in '{niche}'\n"
            f"- Content format detected: '{fmt.replace('_', ' ')}'\n"
            f"- Hook style: '{hook.replace('_', ' ')}'\n"
            f"- Trend alignment score: {trend_score}/100\n"
            f"- Novelty score: {novelty_score}/100 (saturation level: {saturation})\n"
            f"Use this to inform hook strength, pacing, and trend_match_score. "
            f"If saturation is high, push the creator to add a specific personal angle or contrarian take. "
            f"Cite the pattern classification in trend_match_explanation."
        )


_service: Optional[TrendAlignmentService] = None


def get_trend_service() -> TrendAlignmentService:
    global _service
    if _service is None:
        _service = TrendAlignmentService()
    return _service
