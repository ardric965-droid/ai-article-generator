import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

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


def build_prompt(rows: list[dict[str, str]]) -> str:
    """Build the user prompt sent to the Groq chat completion API.

    The prompt template in ``prompts/article_prompt.txt`` expects the rows to
    be inserted at the ``{{ROWS_JSON}}`` placeholder as a JSON array of
    ``{title, description}`` objects. We fill that placeholder directly with
    ``str.replace`` so literal braces in the template never need escaping.
    """
    prompt_dir = getattr(settings, 'PROMPTS_DIR', settings.BASE_DIR / 'prompts')
    prompt_path = prompt_dir / 'article_prompt.txt'

    if not prompt_path.is_file():
        raise LLMConfigurationError(
            f"LLM prompt template file not found at '{prompt_path}'."
        )

    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            template = f.read()
    except Exception as exc:
        raise LLMConfigurationError(
            f"Failed to read prompt template file: {exc}"
        ) from exc

    rows_json = json.dumps(rows, ensure_ascii=False)

    if '{{ROWS_JSON}}' not in template:
        raise LLMConfigurationError(
            "Prompt template is missing the required {{ROWS_JSON}} placeholder "
            "for the row data."
        )

    return template.replace('{{ROWS_JSON}}', rows_json)


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
        'response_format': {'type': 'json_object'},
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


def _validate_article_payload(data: Any, response_text: str) -> list[dict]:
    """Validate the LLM response and return a list of article objects.

    The LLM may return either a JSON array of ``{title, description, article}``
    objects or a single article object. Both formats are accepted.
    """
    if isinstance(data, list):
        articles = data
    elif isinstance(data, dict):
        if all(key in data for key in ('title', 'description', 'article')):
            articles = [data]
        else:
            for value in data.values():
                if isinstance(value, list):
                    articles = value
                    break
            else:
                raise LLMRequestError(
                    f"LLM did not return a JSON array of articles. Response content: {response_text}"
                )
    else:
        raise LLMRequestError(
            f"LLM response must be a JSON array or a single article object. "
            f"Got {type(data).__name__}. Response content: {response_text}"
        )

    for article_obj in articles:
        if not isinstance(article_obj, dict):
            raise LLMRequestError(
                f"LLM response contains a non-object article entry. Response content: {response_text}"
            )

        required_keys = ['title', 'description', 'article']
        missing_keys = [key for key in required_keys if key not in article_obj]
        if missing_keys:
            raise LLMRequestError(
                f"LLM response is missing required keys: {', '.join(missing_keys)}. "
                f"Response content: {response_text}"
            )

        for key in required_keys:
            value = article_obj[key]
            if not isinstance(value, str) or not value.strip():
                raise LLMRequestError(
                    f"LLM response field '{key}' must be a non-empty string. "
                    f"Response content: {response_text}"
                )

    return articles


def generate_article(
    title: str,
    description: str,
    *,
    timeout: int = DEFAULT_REQUEST_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> str:
    """Generate an article for the given title and description using Groq."""
    api_key = _get_api_key()

    # The prompt template expects a JSON array of rows, so wrap this single
    # title/description pair in a one-element list.
    rows = [{'title': title, 'description': description}]

    # Generate the prompt, which also checks if prompts/article_prompt.txt is available
    prompt_content = build_prompt(rows)
    
    messages = [
        {
            'role': 'system',
            'content': (
                'You are a helpful writing assistant that produces structured articles in JSON.'
            ),
        },
        {
            'role': 'user',
            'content': prompt_content,
        },
    ]

    last_error: Exception | None = None
    response_text = ""

    for attempt in range(1, max_retries + 1):
        try:
            response_text = call_groq_chat_completion(
                api_key=api_key,
                messages=messages,
                timeout=timeout,
            )
            break
        except LLMTemporaryError as exc:
            last_error = exc
            if attempt == max_retries:
                raise LLMRequestError(
                    f'Failed to generate article after {max_retries} attempts: {last_error}'
                ) from last_error
            time.sleep(2 ** (attempt - 1))

    # Parse and validate the response
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise LLMRequestError(
            f"LLM response is not a valid JSON object: {exc}\nResponse content: {response_text}"
        ) from exc

    articles = _validate_article_payload(data, response_text)
    if len(articles) != 1:
        raise LLMRequestError(
            f"LLM returned {len(articles)} articles but exactly 1 was expected. "
            f"Response content: {response_text}"
        )
    return articles[0]['article'].strip()

