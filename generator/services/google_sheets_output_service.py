"""Google Sheets output service.

.. deprecated::
    This module is deprecated and is no longer part of the core workflow
    per the authoritative design in ``AGENTS.md`` and ``REFACTOR_NOTES.md``.
    Results are now written back to the **same input Google Sheet** under the
    ``content``, ``status``, and ``error`` columns. This file is retained for
    reference only and may be removed in a future cleanup phase.
"""

import os
from datetime import datetime

from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from generator.models import ArticleResult
from generator.services.google_sheets_service import get_google_sheets_service

# Output sheet columns (see REFACTOR_NOTES.md -> "Google Sheet columns").
OUTPUT_COLUMNS = ['title', 'description', 'content', 'status', 'error']

SPREADSHEET_URL_TEMPLATE = 'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit'

# Drive scope is needed to share the new spreadsheet with the user.
DRIVE_API_SCOPE = 'https://www.googleapis.com/auth/drive'


class GoogleSheetsOutputError(Exception):
    """Base exception for all output Google Sheet operations."""


class OutputSheetCreationError(GoogleSheetsOutputError):
    """Raised when the new output spreadsheet cannot be created."""


class OutputSheetWriteError(GoogleSheetsOutputError):
    """Raised when results cannot be written to the output spreadsheet."""


class OutputSheetShareError(GoogleSheetsOutputError):
    """Raised when the output spreadsheet cannot be shared with the user."""


def _get_drive_service():
    """Build and return the Google Drive API client used to share sheets."""
    creds_path = settings.GOOGLE_CREDENTIALS_FILE
    if not creds_path or not os.path.exists(creds_path):
        raise GoogleSheetsOutputError(
            f"Google credentials file not found at '{creds_path}'. "
            'Please configure GOOGLE_CREDENTIALS_FILE in .env or settings.py.'
        )

    try:
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=[DRIVE_API_SCOPE],
        )
        return build('drive', 'v3', credentials=credentials, cache_discovery=False)
    except Exception as exc:
        raise GoogleSheetsOutputError(
            f'Failed to authenticate or initialize Google Drive client: {exc}'
        ) from exc


def create_output_spreadsheet(*, title: str | None = None) -> str:
    """Create a new, empty Google Sheet and return its spreadsheet ID.

    The spreadsheet is owned by the service account, so it can later be
    shared with the logged-in user through the Drive API.
    """
    display_title = title or f'AI Articles - {datetime.now():%Y-%m-%d %H:%M}'
    service = get_google_sheets_service()

    body = {
        'properties': {
            'title': display_title,
        },
    }

    try:
        spreadsheet = service.spreadsheets().create(body=body).execute()
    except HttpError as exc:
        raise OutputSheetCreationError(
            f'Google Sheets API returned an error while creating the sheet: {exc.reason}'
        ) from exc
    except Exception as exc:
        raise OutputSheetCreationError(
            f'Failed to create the output sheet: {exc}'
        ) from exc

    spreadsheet_id = spreadsheet.get('spreadsheetId')
    if not spreadsheet_id:
        raise OutputSheetCreationError(
            'Google Sheets API did not return a spreadsheetId for the new sheet.'
        )

    return spreadsheet_id


def write_results_to_sheet(spreadsheet_id: str, articles: list[ArticleResult]) -> None:
    """Write the header row plus one data row per ``ArticleResult``."""
    if not articles:
        raise OutputSheetWriteError(
            'At least one ArticleResult is required to fill the output sheet.'
        )

    sorted_articles = sorted(articles, key=lambda article: article.row_number)
    service = get_google_sheets_service()

    # Determine the title of the first sheet in the new spreadsheet.
    try:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id
        ).execute()
        sheets = spreadsheet.get('sheets', [])
        if not sheets:
            raise GoogleSheetsOutputError('The output spreadsheet contains no sheets.')
        first_sheet_title = sheets[0]['properties']['title']
    except HttpError as exc:
        if exc.resp.status == 404:
            raise OutputSheetWriteError(
                f'Output spreadsheet not found for ID {spreadsheet_id!r}.'
            ) from exc
        raise OutputSheetWriteError(
            f'Google Sheets API returned an error while reading the output sheet: {exc.reason}'
        ) from exc
    except GoogleSheetsOutputError:
        raise
    except Exception as exc:
        raise OutputSheetWriteError(
            f'Failed to read output spreadsheet metadata: {exc}'
        ) from exc

    rows = [list(OUTPUT_COLUMNS)]
    for article in sorted_articles:
        rows.append([
            article.title,
            article.description,
            article.article or '',
            article.status,
            article.error_message or '',
        ])

    range_name = f"'{first_sheet_title}'!A1"
    try:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            body={'values': rows},
        ).execute()
    except HttpError as exc:
        raise OutputSheetWriteError(
            f'Google Sheets API returned an error while writing results: {exc.reason}'
        ) from exc
    except Exception as exc:
        raise OutputSheetWriteError(
            f'Failed to write results to the output sheet: {exc}'
        ) from exc


def share_sheet_with_user(spreadsheet_id: str, user_email: str | None) -> None:
    """Give the given user email editor access to the new spreadsheet."""
    if not user_email or not str(user_email).strip():
        raise OutputSheetShareError(
            'A non-empty user email address is required to share the output sheet.'
        )

    user_email = str(user_email).strip()
    drive_service = _get_drive_service()

    permission_body = {
        'type': 'user',
        'role': 'writer',
        'emailAddress': user_email,
    }

    try:
        drive_service.permissions().create(
            fileId=spreadsheet_id,
            body=permission_body,
            sendNotificationEmail=False,
        ).execute()
    except HttpError as exc:
        if exc.resp.status == 403:
            raise OutputSheetShareError(
                f'Google Drive denied sharing the sheet with {user_email}: {exc.reason}'
            ) from exc
        raise OutputSheetShareError(
            f'Google Drive API returned an error while sharing the sheet: {exc.reason}'
        ) from exc
    except Exception as exc:
        raise OutputSheetShareError(
            f'Failed to share the output sheet with {user_email}: {exc}'
        ) from exc


def build_spreadsheet_url(spreadsheet_id: str) -> str:
    """Return a shareable URL for the given spreadsheet ID."""
    return SPREADSHEET_URL_TEMPLATE.format(spreadsheet_id=spreadsheet_id)


def create_and_populate_output_sheet(
    articles: list[ArticleResult],
    user_email: str | None,
    *,
    spreadsheet_title: str | None = None,
) -> str:
    """Create the output sheet, write results, share it, and return its URL.

    This is the main entry point the processing service calls when a
    generation job finishes.
    """
    spreadsheet_id = create_output_spreadsheet(title=spreadsheet_title)
    write_results_to_sheet(spreadsheet_id, articles)
    share_sheet_with_user(spreadsheet_id, user_email)
    return build_spreadsheet_url(spreadsheet_id)