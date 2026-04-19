"""
DatasetLoader — loads the YouTube trending CSV and pre-computes per-niche stats.
Stats are computed once at startup and cached in memory.
Gracefully skips if CSV is not present.
"""
from __future__ import annotations
import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# YouTube category_id → niche cluster mapping
CATEGORY_TO_NICHE: dict[int, list[str]] = {
    1:  ["lifestyle & vlogs"],
    2:  ["tech & gadgets"],
    10: ["lifestyle & vlogs"],
    15: ["lifestyle & vlogs"],
    17: ["fitness & health"],
    19: ["travel"],
    20: ["gaming"],
    22: ["lifestyle & vlogs", "self improvement", "personal finance"],
    23: ["lifestyle & vlogs"],
    24: ["true crime", "lifestyle & vlogs"],
    25: ["personal finance", "business & entrepreneurship", "true crime"],
    26: ["fitness & health", "cooking & food", "self improvement"],
    27: ["education & learning", "science & nature", "self improvement"],
    28: ["tech & gadgets", "science & nature", "business & entrepreneurship"],
    29: ["education & learning"],
}

# Reverse: niche keyword → list of category IDs
NICHE_KEYWORD_TO_CATS: dict[str, list[int]] = {
    "personal finance":             [25, 22],
    "fitness":                      [26, 17],
    "health":                       [26, 17],
    "tech":                         [28, 2],
    "gadgets":                      [28, 2],
    "business":                     [28, 25, 22],
    "entrepreneurship":             [25, 22, 28],
    "gaming":                       [20],
    "education":                    [27, 29],
    "learning":                     [27, 29],
    "lifestyle":                    [22, 1, 23],
    "vlogs":                        [22, 1],
    "cooking":                      [26],
    "food":                         [26],
    "travel":                       [19],
    "self improvement":             [22, 26, 27],
    "true crime":                   [24, 25],
    "science":                      [28, 27],
    "nature":                       [28, 27],
}


def _niche_to_category_ids(niche: str) -> list[int]:
    """Map a user-supplied niche string to YouTube category IDs."""
    niche_lower = niche.lower()
    cats: set[int] = set()
    for keyword, ids in NICHE_KEYWORD_TO_CATS.items():
        if keyword in niche_lower:
            cats.update(ids)
    return list(cats) if cats else list(range(1, 30))  # fallback: all categories


class NicheStats:
    """Pre-computed statistics for one niche/category cluster."""

    def __init__(self, data: dict):
        self.row_count: int = data.get("row_count", 0)
        self.median_engagement: float = data.get("median_engagement", 0.04)
        self.median_like_rate: float = data.get("median_like_rate", 0.03)
        self.p75_engagement: float = data.get("p75_engagement", 0.08)
        self.p90_engagement: float = data.get("p90_engagement", 0.15)
        # {pattern_name: {"count": int, "avg_engagement": float, "avg_views": float}}
        self.pattern_stats: dict = data.get("pattern_stats", {})
        # {format_name: {"count": int, "avg_engagement": float, "avg_views": float}}
        self.format_stats: dict = data.get("format_stats", {})
        self.avg_title_length: float = data.get("avg_title_length", 55.0)
        self.top_patterns: list[str] = data.get("top_patterns", [])
        self.top_formats: list[str] = data.get("top_formats", [])
        self.saturation_map: dict[str, int] = data.get("saturation_map", {})

    def saturation_level(self, pattern: str) -> str:
        """Return low/medium/high saturation for a title pattern."""
        count = self.saturation_map.get(pattern, 0)
        if count == 0:
            return "unknown"
        pct = count / max(self.row_count, 1)
        if pct > 0.30:
            return "high"
        if pct > 0.15:
            return "medium"
        return "low"

    def pattern_engagement_rank(self, pattern: str) -> int:
        """1-based rank of pattern by avg_engagement within this niche (1=best)."""
        ranked = sorted(
            self.pattern_stats.items(),
            key=lambda x: x[1].get("avg_engagement", 0),
            reverse=True,
        )
        for i, (name, _) in enumerate(ranked, 1):
            if name == pattern:
                return i
        return len(ranked) + 1


class DatasetLoader:
    """
    Loads the YouTube trending CSV, pre-computes per-niche stats.
    Falls back gracefully if CSV is absent.
    """

    def __init__(self, csv_path: str):
        self._csv_path = csv_path
        self._loaded = False
        self._niche_cache: dict[str, NicheStats] = {}
        self._global_stats: Optional[NicheStats] = None
        self._load()

    def is_loaded(self) -> bool:
        return self._loaded

    def _load(self) -> None:
        if not os.path.exists(self._csv_path):
            logger.warning("Dataset CSV not found at %s — dataset signals will use heuristics only", self._csv_path)
            return
        try:
            import pandas as pd
            from services.dataset.pattern_classifier import get_classifier
            clf = get_classifier()

            logger.info("Loading YouTube trending dataset from %s…", self._csv_path)
            df = pd.read_csv(self._csv_path, low_memory=False)
            logger.info("Loaded %d rows, %d cols", len(df), len(df.columns))

            # Ensure numeric columns
            for col in ["views", "likes", "dislikes", "comment_count",
                        "engagement_rate", "like_rate", "comment_rate",
                        "days_to_trend", "title_length", "category_id"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            if "engagement_rate" not in df.columns:
                df["engagement_rate"] = (df.get("likes", 0) + df.get("comment_count", 0)) / df["views"].replace(0, 1)
            if "like_rate" not in df.columns:
                df["like_rate"] = df.get("likes", 0) / df["views"].replace(0, 1)

            # Classify title patterns for all rows (fast, regex only)
            logger.info("Classifying title patterns…")
            df["_title_pattern"] = df["title"].fillna("").apply(clf.classify_title_pattern)
            df["_content_format"] = df["title"].fillna("").apply(
                lambda t: clf.classify_content_format(t, "", "")
            )

            # Compute global stats
            self._global_stats = self._compute_stats(df)

            # Pre-compute per-niche stats for all known niches
            all_niches = list(NICHE_KEYWORD_TO_CATS.keys())
            for niche in all_niches:
                cat_ids = _niche_to_category_ids(niche)
                subset = df[df["category_id"].isin(cat_ids)] if "category_id" in df.columns else df
                if len(subset) >= 50:
                    self._niche_cache[niche] = self._compute_stats(subset)

            self._loaded = True
            logger.info("Dataset intelligence ready — %d niches pre-computed", len(self._niche_cache))

        except Exception as exc:
            logger.error("Dataset loading failed: %s", exc, exc_info=True)

    def _compute_stats(self, df) -> NicheStats:
        import numpy as np
        eng = df["engagement_rate"].dropna()
        like = df["like_rate"].dropna() if "like_rate" in df.columns else eng

        # Pattern stats
        pattern_stats: dict = {}
        if "_title_pattern" in df.columns:
            for pname, grp in df.groupby("_title_pattern"):
                pattern_stats[str(pname)] = {
                    "count": len(grp),
                    "avg_engagement": float(grp["engagement_rate"].mean() or 0),
                    "avg_views": float(grp["views"].mean() or 0) if "views" in grp.columns else 0,
                }

        format_stats: dict = {}
        if "_content_format" in df.columns:
            for fname, grp in df.groupby("_content_format"):
                format_stats[str(fname)] = {
                    "count": len(grp),
                    "avg_engagement": float(grp["engagement_rate"].mean() or 0),
                    "avg_views": float(grp["views"].mean() or 0) if "views" in grp.columns else 0,
                }

        top_patterns = sorted(
            pattern_stats.keys(),
            key=lambda k: pattern_stats[k]["avg_engagement"],
            reverse=True,
        )[:4]

        top_formats = sorted(
            format_stats.keys(),
            key=lambda k: format_stats[k]["avg_engagement"],
            reverse=True,
        )[:4]

        saturation_map = {k: v["count"] for k, v in pattern_stats.items()}

        return NicheStats({
            "row_count": len(df),
            "median_engagement": float(eng.median() or 0.04),
            "median_like_rate": float(like.median() or 0.03),
            "p75_engagement": float(np.percentile(eng, 75) if len(eng) > 0 else 0.08),
            "p90_engagement": float(np.percentile(eng, 90) if len(eng) > 0 else 0.15),
            "pattern_stats": pattern_stats,
            "format_stats": format_stats,
            "avg_title_length": float(df["title"].fillna("").str.len().mean() or 55.0),
            "top_patterns": top_patterns,
            "top_formats": top_formats,
            "saturation_map": saturation_map,
        })

    def get_niche_stats(self, niche: str) -> NicheStats:
        """Return pre-computed stats for the closest matching niche."""
        niche_lower = niche.lower()
        # Exact or partial match
        for key in self._niche_cache:
            if key in niche_lower or niche_lower in key:
                return self._niche_cache[key]
        # Fallback to global
        return self._global_stats or NicheStats({})


_loader: Optional[DatasetLoader] = None


def get_dataset_loader() -> DatasetLoader:
    global _loader
    if _loader is None:
        from core.config import settings
        _loader = DatasetLoader(settings.dataset_csv_path)
    return _loader
