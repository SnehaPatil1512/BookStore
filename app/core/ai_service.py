"""AI summary provider integration."""

import logging

import httpx

from app.core.config import SETTINGS


class SummaryProviderError(Exception):
    """Raised when the summary provider fails."""


logger = logging.getLogger(__name__)


def summarize_book(content: str) -> str:
    """Generate a concise summary using the configured AI provider."""
    if not SETTINGS.openrouter_api_key:
        raise SummaryProviderError("AI provider key is not configured.")

    payload = {
        "model": SETTINGS.summary_model,
        "messages": [
            {
                "role": "user",
                "content": f"Summarize this book in 5 simple lines:\n{content[:2000]}",
            }
        ],
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                SETTINGS.summary_api_url,
                headers={
                    "Authorization": f"Bearer {SETTINGS.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException as exc:
        logger.warning("Summary provider request timed out.")
        raise SummaryProviderError("AI provider timed out. Please try again.") from exc
    except httpx.HTTPStatusError as exc:
        logger.warning("Summary provider HTTP status error: %s", exc.response.status_code)
        raise SummaryProviderError("AI provider request failed.") from exc
    except httpx.HTTPError as exc:
        logger.warning("Summary provider HTTP transport error: %s", exc)
        raise SummaryProviderError("AI provider request failed.") from exc
    except ValueError as exc:
        logger.warning("Summary provider returned invalid JSON.")
        raise SummaryProviderError("AI provider returned invalid JSON.") from exc

    summary_text = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    if not summary_text:
        provider_message = data.get("error", {}).get("message")
        if provider_message:
            raise SummaryProviderError(provider_message)
        raise SummaryProviderError("AI provider returned an empty summary.")

    return summary_text
