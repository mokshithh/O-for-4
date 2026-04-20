"""Shared utilities for AI response parsing and retry logic."""
from __future__ import annotations
import json
import re


def parse_json_response(raw: str) -> dict | list:
    """Strip markdown fences and parse JSON from LLM output."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```\s*$", "", raw, flags=re.MULTILINE)
    raw = raw.strip()
    return json.loads(raw)
