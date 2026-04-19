"""
PatternClassifierService — deterministic regex/rule-based classifiers.
Works without the CSV. Used on any title/tags/description text.
"""
from __future__ import annotations
import re


# ── Title pattern taxonomy ────────────────────────────────────────────────

TITLE_PATTERNS = {
    "question_curiosity": [
        r"\?$",
        r"^(why|what|how|when|who|which|is|are|do|does|did|should|would|could|will|can)\b",
        r"\b(secret|truth|real reason|actually|really)\b",
    ],
    "hype_announcement": [
        r"!",
        r"\b(breaking|announcing|reveal|launch|just dropped|new|finally|exclusive)\b",
        r"\b(you won't believe|unbelievable|shocking|insane|crazy|mindblowing)\b",
    ],
    "number_list": [
        r"^\d+\s+(reasons?|ways?|tips?|tricks?|things?|steps?|mistakes?|habits?|rules?|facts?|secrets?|hacks?)",
        r"^\d+\s+\w+\s+(reasons?|ways?|tips?|tricks?|things?|steps?|mistakes?|habits?|rules?|facts?|secrets?|hacks?)",
        r"\b\d+\s+(reasons?|ways?|tips?|tricks?|things?|steps?|mistakes?|habits?|rules?|facts?|secrets?|hacks?)\b",
        r"\b\d+\s+\w+\s+(reasons?|ways?|tips?|tricks?|things?|steps?|mistakes?|habits?|rules?|facts?|secrets?|hacks?)\b",
        r"^(top|best)\s+\d+",
    ],
    "problem_truth": [
        r"\b(stop|quit|never|avoid|don't|mistake|wrong|broken|lied|lie|scam|fraud|myth|toxic)\b",
        r"\b(truth about|problem with|dark side|ugly truth|honest|blunt|real talk)\b",
        r"\b(nobody tells you|they don't want you to know|what they won't tell)\b",
    ],
    "challenge_experiment": [
        r"\b(i tried|i tested|i spent|i quit|i stopped|i challenged|days?|weeks?|months?)\b.*\b(and|to see|to find)\b",
        r"\b(challenge|experiment|test|tried for|living on|only eating|vs\.?)\b",
        r"\b(\d+ day|\d+ week|\d+ month)\b",
    ],
    "reveal_result": [
        r"\b(how i (made|earned|built|lost|gained|saved)|my results?|what happened|it worked|it failed)\b",
        r"\b(review|reaction|response|update|follow.?up|the result|after \d+)\b",
        r"\b(honest review|real results?|case study|breakdown|analysis)\b",
    ],
}

CONTENT_FORMATS = {
    "explainer": [
        r"\b(how to|how i|explained?|guide|tutorial|beginners?|learn|understand|everything you need)\b",
        r"\b(complete guide|ultimate guide|full guide|step by step)\b",
    ],
    "commentary": [
        r"\b(my thoughts?|opinion|take|rant|response to|reacting to|thoughts on|talking about)\b",
        r"\b(why i (think|believe|hate|love)|let's talk|we need to talk)\b",
    ],
    "story": [
        r"\b(my story|story time|i was|how i (went|became|started|ended up)|journey)\b",
        r"\b(the day|what happened|confession|i finally|i quit|i left)\b",
    ],
    "challenge": [
        r"\b(challenge|i tried|i tested|vs\.?|\d+ day(s)? of|only .* for \d+)\b",
    ],
    "reaction": [
        r"\b(react(ion|ing)|watch(ing|ed)|reacts?|watching)\b",
    ],
    "review": [
        r"\b(review|unboxing|hands.?on|first look|is it worth|should you buy|honest review)\b",
    ],
    "announcement": [
        r"\b(announcing|i'm (leaving|quitting|moving|starting|launching)|big news|update|channel update)\b",
    ],
}

HOOK_STYLES = {
    "curiosity_gap": [
        r"\b(secret|truth|real reason|nobody knows|they won't tell|hidden|actually)\b",
        r"\?.*\b(you|we|i)\b",
    ],
    "direct_value": [
        r"^(how to|the \d+|here('s| is)|learn|get|build|make|earn|save)\b",
        r"\b(step by step|exactly how|the complete|everything you need)\b",
    ],
    "controversy": [
        r"\b(unpopular opinion|hot take|controversial|disagree|wrong about|actually bad|overrated|underrated)\b",
        r"\b(nobody wants to hear|harsh truth|don't @ me)\b",
    ],
    "story_teaser": [
        r"\b(story time|this happened|i never thought|i can't believe|the day i|it all started)\b",
    ],
    "number_promise": [
        r"^\d+\s+\w+",
        r"\b(top \d+|best \d+|\d+ ways?|\d+ reasons?)\b",
    ],
    "question": [
        r"\?",
        r"^(why|what|how|is|are|do|does|should|would)\b",
    ],
}


class PatternClassifier:
    """Classifies title pattern, content format, and hook style using rules."""

    def classify_title_pattern(self, title: str) -> str:
        title_lower = title.lower()
        scores: dict[str, int] = {}
        for pattern_name, rules in TITLE_PATTERNS.items():
            count = sum(1 for r in rules if re.search(r, title_lower))
            if count:
                scores[pattern_name] = count
        if not scores:
            return "generic_descriptive"
        return max(scores, key=scores.__getitem__)

    def classify_content_format(self, title: str, tags: str = "", description: str = "") -> str:
        text = f"{title} {tags} {description[:200]}".lower()
        scores: dict[str, int] = {}
        for fmt, rules in CONTENT_FORMATS.items():
            count = sum(1 for r in rules if re.search(r, text))
            if count:
                scores[fmt] = count
        if not scores:
            return "other"
        return max(scores, key=scores.__getitem__)

    def classify_hook_style(self, title: str) -> str:
        title_lower = title.lower()
        scores: dict[str, int] = {}
        for style, rules in HOOK_STYLES.items():
            count = sum(1 for r in rules if re.search(r, title_lower))
            if count:
                scores[style] = count
        if not scores:
            return "direct_value"
        return max(scores, key=scores.__getitem__)

    def classify_all(self, title: str, tags: str = "", description: str = "") -> dict:
        return {
            "title_pattern": self.classify_title_pattern(title),
            "content_format": self.classify_content_format(title, tags, description),
            "hook_style": self.classify_hook_style(title),
        }


_classifier: PatternClassifier | None = None


def get_classifier() -> PatternClassifier:
    global _classifier
    if _classifier is None:
        _classifier = PatternClassifier()
    return _classifier
