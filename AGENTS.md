# AI Article Generator – Agent Guidelines

This document describes how AI agents (including GitHub Copilot, Cline, etc.) should understand and modify the Django AI Article Generator project.

## Project overview

This is a beginner-level Django AI Article Generator for a junior/intern technical assessment.

The app:

- Requires users to log in (Django’s built-in authentication).
- Reads article inputs (`title`, `description`) from a Google Sheet the user shares with the service account.
- Generates one article per row using an LLM API.
- Writes the generated articles back into the **same Google Sheet** under `content`, `status`, and `error` columns.

## Current development setup

- VS Code
- GitHub Copilot
- Python
- Django
- SQLite
- Google Sheets API (service account with `credentials.json`)
- LLM API
- `threading.Thread`
- Django templates
- HTML/CSS
- Vanilla JavaScript
- Git/GitHub

## Authentication

- Use Django’s built-in authentication system (`django.contrib.auth`).
- Users must log in to access the article generation feature.
- Use the default `User` model (or existing custom user model if already in use).
- Add login/logout views and URLs if they don’t exist.
- Protect all article-generation views with `@login_required`.
- The logged-in user’s email (`request.user.email`) is used for logging/auditing where needed, but **not** for Google Sheet sharing in the current design.

## Agreed workflow

1. The user must be logged in (Django’s built-in authentication).
2. The user creates a Google Sheet with `title` and `description` columns.
3. The user shares that sheet with the Django service account email (so the app can read and write it).
4. The user pastes the Google Sheet URL into a Django form.
5. Django extracts the spreadsheet ID.
6. Django reads the rows through the Google Sheets API.
7. Django generates one article per row using an LLM API.
8. Django writes the generated articles back into the **same Google Sheet**, using columns:
   - `content`
   - `status`
   - `error`
9. The user sees progress in the Django UI and opens the same Google Sheet to view results.

The app **does not create a new Google Sheet**. All results are written back to the user’s original sheet.

## Google Sheet columns

Single Google Sheet (user-provided, shared with service account):

- Input columns:
  - `title`
  - `description`
- Output columns (written by the app):
  - `content`
  - `status`
  - `error`

The app never creates a new Google Sheet; it only reads and updates this sheet.

## LLM response format

The LLM should return JSON such as:

```json
[
  {
    "title": "Article title",
    "description": "Short description",
    "article": "Complete article text"
  }
]
```

For single-row calls, the array will contain exactly one object. The app:

- Parses and validates the JSON.
- Uses the `article` field for the article body.
- Stores `status` and any error messages in the `ArticleResult` model and in the Google Sheet.

## Other requirements

- The Google Sheet can contain any number of valid rows.
- The prompt must be stored outside Python code in:
  `prompts/article_prompt.txt`
- The prompt must be detailed and use a `{{ROWS_JSON}}` placeholder for row data.
- LLM JSON responses must be parsed and validated.
- Use `GenerationJob` and `ArticleResult` models.
- Store the Google Sheet row number in `ArticleResult`.
- Use `threading.Thread` for background processing.
- Use one thread per generation job, not one thread per row.
- The upload request should return immediately.
- Update progress after every row.
- Support cancellation.
- Save progress after cancellation.
- Support resuming a cancelled or failed job.
- Never regenerate rows already marked completed.
- Retry failed or incomplete rows only.
- Use a JSON status endpoint.
- Use vanilla JavaScript fetch polling for progress.
- Show pending, processing, completed, failed, and cancelled statuses.
- Keep Google Sheets and LLM credentials private.
- Store secrets in `.env`.
- Do not use React, Streamlit, Celery, Redis, LangChain, or Docker.

## Models

- `GenerationJob`
  - Standard fields for job metadata (e.g., `status`, `total_rows`, `completed_rows`, `failed_rows`, `spreadsheet_id`, `created_at`, `completed_at`).
  - `user` – optional FK to the Django user who started the job (for logging/auditing).
  - `output_sheet_url` – present from a previous design iteration; **not used** in the current workflow.

- `ArticleResult`
  - `job = models.ForeignKey(GenerationJob, on_delete=models.CASCADE)`
  - `row_number = models.IntegerField()`
  - `title = models.CharField(...)`
  - `description = models.TextField(...)`
  - `content = models.TextField(...)`
  - `status = models.CharField(...)`  # e.g. pending, processing, completed, failed, cancelled
  - `error = models.TextField(blank=True, null=True)`

## Recommended file responsibilities

- `models.py`: `GenerationJob` and `ArticleResult`
- `views.py`: request handling, authentication-protected views
- `urls.py`: URL routing (including login/logout if custom)
- `google_sheets_service.py`:
  - Read `title`/`description` rows from the user’s sheet.
  - Write `content`/`status`/`error` back into the same sheet.
- `llm_service.py`:
  - Load prompt from `prompts/article_prompt.txt`.
  - Build prompts using `{{ROWS_JSON}}`.
  - Call LLM and parse/validate JSON array responses.
- `processing_service.py`: background processing, cancellation, and resume
- `prompts/article_prompt.txt`: detailed LLM prompt
- `templates/`: HTML pages (including login/logout and job status)
- `static/`: CSS and JavaScript
- `tests/`: automated tests

Note: `google_sheets_output_service.py` (if present) is **deprecated** and no longer part of the core workflow.

## Implementation phases (current)

1. Django authentication (login/logout, `@login_required` on generation views) ✅
2. Google Sheets connection and URL validation (input sheet, shared with service account) ✅
3. Read `title` and `description` rows from input sheet ✅
4. Add external prompt file ✅
5. LLM JSON response and validation ✅
6. Write `content`/`status`/`error` back to the same Google Sheet ✅ (primary path)
7. Cancellation and resume ✅
8. Progress polling ✅
9. Tests and documentation ✅
10. Cleanup: remove deprecated output-sheet code (optional)

## Guidance for AI agents

- Treat this file and `REFACTOR_NOTES.md` as the authoritative design.
- If anything in older docs or code comments conflicts with this file, follow this file and update the other files accordingly.
- Work in small phases.
- Before changing any file, inspect its current content.
- After each phase, summarize what changed and how to test it.
- Do not rewrite working code unnecessarily.
- Do not modify unrelated files.