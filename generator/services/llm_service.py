import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

GROQ_CHAT_COMPLETIONS_URL = 'https://api.groq.com/openai/v1/chat/completions'
DEFAULT_GROQ_MODEL = 'llama-3.3-70b-versatile'
DEFAULT_REQUEST_TIMEOUT = 60
DEFAULT_MAX_RETRIES = 3
GROQ_USER_AGENT = 'ai-article-generator/1.0'
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
PLACEHOLDER_API_KEYS = frozenset({
    '',
    'your-api-key-here',
    'your_real_key_here',
})


class LLMConfigurationError(Exception):
    """Raised when the LLM service is not configured correctly."""


class LLMRequestError(Exception):
    """Raised when the LLM provider rejects or cannot fulfill a request."""


class LLMTemporaryError(Exception):
    """Raised for transient failures that may succeed on retry."""


def build_prompt(title: str, description: str) -> str:
    """Build the user prompt sent to the Groq chat completion API."""
    return (
        'Write a clear, engaging article based on the following input.\n\n'
        f'Title: {title.strip()}\n'
        f'Description: {description.strip()}\n\n'
        'Return only the article text.'
    )


def _get_api_key() -> str:
    api_key = os.environ.get('LLM_API_KEY', '').strip()
    if not api_key or api_key in PLACEHOLDER_API_KEYS:
        raise LLMConfigurationError(
            'LLM_API_KEY is missing. Add your Groq API key to the .env file.'
        )
    return api_key


def _get_model() -> str:
    return os.environ.get('GROQ_MODEL', DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL


def call_groq_chat_completion(
    *,
    api_key: str,
    messages: list[dict[str, str]],
    timeout: int = DEFAULT_REQUEST_TIMEOUT,
    model: str | None = None,
) -> str:
    """Call the Groq chat completions API and return the generated text.

    This function contains all Groq-specific HTTP logic and is intended to be
    mocked in tests so the real API is never contacted.
    """
    payload = {
        'model': model or _get_model(),
        'messages': messages,
        'temperature': 0.7,
    }
    request_data = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        GROQ_CHAT_COMPLETIONS_URL,
        data=request_data,
        method='POST',
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': GROQ_USER_AGENT,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode('utf-8')
            status_code = response.getcode()
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        response_body = exc.read().decode('utf-8', errors='replace')
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise LLMTemporaryError(
                f'Groq API request timed out after {timeout} seconds.'
            ) from exc
        raise LLMTemporaryError(
            f'Could not reach the Groq API: {exc.reason}'
        ) from exc

    if status_code in RETRYABLE_STATUS_CODES:
        raise LLMTemporaryError(
            f'Groq API returned temporary error {status_code}: {response_body}'
        )

    if status_code >= 400:
        raise LLMRequestError(
            f'Groq API request failed with status {status_code}: {response_body}'
        )

    try:
        data: dict[str, Any] = json.loads(response_body)
        return data['choices'][0]['message']['content'].strip()
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise LLMRequestError(
            'Groq API returned an unexpected response format.'
        ) from exc


def generate_article(
    title: str,
    description: str,
    *,
    timeout: int = DEFAULT_REQUEST_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> str:
    """Generate an article for the given title and description using Groq."""
    api_key = _get_api_key()
    messages = [
        {
            'role': 'system',
            'content': (
                'You are a helpful writing assistant that produces well-structured '
                'articles in plain text.'
            ),
        },
        {
            'role': 'user',
            'content': build_prompt(title, description),
        },
    ]

    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return call_groq_chat_completion(
                api_key=api_key,
                messages=messages,
                timeout=timeout,
            )
        except LLMTemporaryError as exc:
            last_error = exc
            if attempt == max_retries:
                break
            time.sleep(2 ** (attempt - 1))

    raise LLMRequestError(
        f'Failed to generate article after {max_retries} attempts: {last_error}'
    ) from last_error
