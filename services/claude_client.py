"""AI chat client — uses OpenAI GPT-4o with retry logic."""
import time
import logging
from openai import OpenAI, RateLimitError, APIStatusError
from core.config import settings

logger = logging.getLogger(__name__)
_client: OpenAI | None = None

_RETRY_STATUSES = {429, 500, 502, 503, 504}


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def _call(model: str, system: str, user: str, max_tokens: int, temperature: float, seed: int) -> str:
    client = get_client()
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                seed=seed,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return response.choices[0].message.content
        except RateLimitError:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            logger.warning("Rate limited — retrying in %ds", wait)
            time.sleep(wait)
        except APIStatusError as exc:
            if exc.status_code not in _RETRY_STATUSES or attempt == 2:
                raise
            wait = 2 ** attempt
            logger.warning("OpenAI %d — retrying in %ds", exc.status_code, wait)
            time.sleep(wait)
    raise RuntimeError("OpenAI call failed after 3 attempts")


def chat(system: str, user: str, max_tokens: int = 2048, temperature: float = 0.0, seed: int = 42) -> str:
    """temperature=0 + seed makes scoring deterministic. Retries on transient errors."""
    return _call("gpt-4o", system, user, max_tokens, temperature, seed)


def cheap_chat(system: str, user: str, max_tokens: int = 512, temperature: float = 0.0, seed: int = 42) -> str:
    """gpt-4o-mini for low-stakes classification/comparison calls."""
    return _call("gpt-4o-mini", system, user, max_tokens, temperature, seed)
