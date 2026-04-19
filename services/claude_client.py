"""AI chat client — uses Anthropic Claude."""
import anthropic
from core.config import settings

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def chat(system: str, user: str, max_tokens: int = 2048, temperature: float = 0.0, seed: int = 42) -> str:
    client = get_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text
