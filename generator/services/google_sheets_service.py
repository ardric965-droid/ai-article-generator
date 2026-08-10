import os
import re
from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class GoogleSheetsError(Exception):
    """Base exception for all Google Sheets service errors."""
    pass

class InvalidSpreadsheetURLError(GoogleSheetsError):
    """Raised when the spreadsheet URL or ID is malformed or invalid."""
    pass

class SpreadsheetNotFoundError(GoogleSheetsError):
    """Raised when the spreadsheet does not exist (HTTP 404)."""
    pass

class SpreadsheetPermissionError(GoogleSheetsError):
    """Raised when access is denied to the spreadsheet (HTTP 403)."""
    pass

class GoogleAPIError(GoogleSheetsError):
    """Raised for any unexpected Google API failures or configuration issues."""
    pass


def extract_spreadsheet_id(url_or_id: str) -> str:
    """Extract and validate the spreadsheet ID from a Google Sheets URL or raw ID string.
    
    Supports various URL structures and raw 44-character (or similar alphanumeric) IDs.
    """
    if not url_or_id:
        raise InvalidSpreadsheetURLError("Spreadsheet URL or ID cannot be empty.")
        
    url_or_id = url_or_id.strip()
    
    # Check for standard URL match
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url_or_id)
    if match:
        return match.group(1)
        
    # Check if raw ID format (alphanumeric, underscores, hyphens)
    if re.match(r'^[a-zA-Z0-9-_]+$', url_or_id):
        return url_or_id
        
    raise InvalidSpreadsheetURLError(
        f"The provided input '{url_or_id}' is not a valid Google Sheets URL or raw Spreadsheet ID."
    )


def get_google_sheets_service():
    """Build and return the Google Sheets API client resource.
    
    Uses settings.GOOGLE_CREDENTIALS_FILE for service account authentication.
    """
    creds_path = settings.GOOGLE_CREDENTIALS_FILE
    if not creds_path or not os.path.exists(creds_path):
        raise GoogleAPIError(
            f"Google credentials file not found at '{creds_path}'. "
            "Please configure GOOGLE_CREDENTIALS_FILE in .env or settings.py."
        )
        
    try:
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=['https://www.googleapis.com/auth/spreadsheets'],
        )
        service = build('sheets', 'v4', credentials=credentials, cache_discovery=False)
        return service
    except Exception as exc:
        raise GoogleAPIError(f"Failed to authenticate or initialize Google Sheets client: {exc}") from exc


def validate_sheet_connection(url_or_id: str) -> str:
    """Validate connection to the Google Sheet by fetching basic metadata.
    
    Returns the extracted Spreadsheet ID on success, or raises a custom exception on error.
    """
    spreadsheet_id = extract_spreadsheet_id(url_or_id)
    service = get_google_sheets_service()
    
    try:
        # Request only the spreadsheetId field to keep the payload minimal
        service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields='spreadsheetId'
        ).execute()
        return spreadsheet_id
    except HttpError as exc:
        status_code = exc.resp.status
        if status_code == 404:
            raise SpreadsheetNotFoundError(
                f"Spreadsheet not found for ID '{spreadsheet_id}'. Please check if the ID/URL is correct."
            ) from exc
        elif status_code in (401, 403):
            raise SpreadsheetPermissionError(
                f"Permission denied accessing spreadsheet '{spreadsheet_id}'. "
                "Please make sure it is shared with the service account."
            ) from exc
        else:
            raise GoogleAPIError(
                f"Google Sheets API returned an error (status {status_code}): {exc.reason}"
            ) from exc
    except Exception as exc:
        raise GoogleAPIError(f"An unexpected error occurred while connecting to Google Sheets: {exc}") from exc


def read_sheet_rows(spreadsheet_id: str) -> list[dict]:
    """Read data rows (titles and descriptions) from the first sheet.
    
    Validates headers and row values. Dynamically appends output headers if missing.
    Returns a list of dicts: [{'row_number': int, 'title': str, 'description': str}]
    """
    service = get_google_sheets_service()
    
    # Get the title of the first sheet
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet.get('sheets', [])
        if not sheets:
            raise GoogleSheetsError("The spreadsheet contains no sheets.")
        first_sheet_title = sheets[0]['properties']['title']
    except HttpError as exc:
        if exc.resp.status == 404:
            raise SpreadsheetNotFoundError(
                f"Spreadsheet not found for ID '{spreadsheet_id}'."
            ) from exc
        elif exc.resp.status in (401, 403):
            raise SpreadsheetPermissionError(
                f"Permission denied accessing spreadsheet '{spreadsheet_id}'."
            ) from exc
        else:
            raise GoogleAPIError(f"Google Sheets API error: {exc.reason}") from exc
    except Exception as exc:
        if isinstance(exc, GoogleSheetsError):
            raise
        raise GoogleAPIError(f"Failed to retrieve spreadsheet metadata: {exc}") from exc
        
    # Read all values from columns A to Z
    range_name = f"'{first_sheet_title}'!A:Z"
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
    except Exception as exc:
        raise GoogleAPIError(f"Failed to read cells from sheet: {exc}") from exc
        
    values = result.get('values', [])
    if not values:
        raise GoogleSheetsError("The sheet is empty.")
        
    headers = values[0]
    if not headers or not any(h.strip() for h in headers):
        raise GoogleSheetsError("The sheet must include a header row.")
        
    # Map headers locally - the input sheet is read-only, so no
    # columns are appended or written back to it.
    header_indices = {
        header: idx
        for idx, header in enumerate(h.strip().lower() if h else '' for h in headers)
        if header
    }
    
    title_idx = header_indices.get('title')
    desc_idx = header_indices.get('description')
    
    if title_idx is None or desc_idx is None:
        raise GoogleSheetsError("The sheet must include 'title' and 'description' columns.")
        
    rows = []
    # Parse rows starting from row 2 (index 1)
    for idx, row in enumerate(values[1:], start=2):
        # Skip completely empty rows
        if not any(str(cell).strip() for cell in row):
            continue
            
        title = ""
        if title_idx < len(row):
            title = str(row[title_idx]).strip()
            
        desc = ""
        if desc_idx < len(row):
            desc = str(row[desc_idx]).strip()
            
        if not title:
            raise GoogleSheetsError(f"Row {idx}: title must not be empty.")
        if not desc:
            raise GoogleSheetsError(f"Row {idx}: description must not be empty.")
            
        rows.append({
            'row_number': idx,
            'title': title,
            'description': desc
        })
        
    if not rows:
        raise GoogleSheetsError("The sheet must contain at least one data row.")
        
    return rows


def _column_letter(zero_based_index: int) -> str:
    """Convert a 0-based column index to its A1-style letter(s)."""
    index = zero_based_index + 1
    letters = ''
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def ensure_result_columns(spreadsheet_id: str, service) -> None:
    """Ensure the first row contains the required result headers.

    Required headers: title, description, content, status, error.
    Any missing headers are appended after the existing headers in the
    first row so results can be written back to the same sheet.
    """
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet.get('sheets', [])
        if not sheets:
            raise GoogleSheetsError("The spreadsheet contains no sheets.")
        first_sheet_title = sheets[0]['properties']['title']
    except HttpError as exc:
        if exc.resp.status == 404:
            raise SpreadsheetNotFoundError(
                f"Spreadsheet not found for ID '{spreadsheet_id}'."
            ) from exc
        elif exc.resp.status in (401, 403):
            raise SpreadsheetPermissionError(
                f"Permission denied accessing spreadsheet '{spreadsheet_id}'."
            ) from exc
        else:
            raise GoogleAPIError(f"Google Sheets API error: {exc.reason}") from exc
    except Exception as exc:
        if isinstance(exc, GoogleSheetsError):
            raise
        raise GoogleAPIError(f"Failed to retrieve spreadsheet metadata: {exc}") from exc

    range_name = f"'{first_sheet_title}'!A1:Z1"
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name,
        ).execute()
    except Exception as exc:
        raise GoogleAPIError(f"Failed to read header row: {exc}") from exc

    values = result.get('values', [[]])
    headers = values[0] if values else []
    normalised = [str(h).strip().lower() if h else '' for h in headers]
    required = ['title', 'description', 'content', 'status', 'error']

    missing = [h for h in required if h not in normalised]
    if not missing:
        return

    updated_headers = list(headers) + missing
    try:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            body={'values': [updated_headers]},
        ).execute()
    except HttpError as exc:
        raise GoogleAPIError(
            f"Google Sheets API returned an error while updating headers: {exc.reason}"
        ) from exc
    except Exception as exc:
        raise GoogleAPIError(f"Failed to update header row: {exc}") from exc


def update_sheet_row(
    spreadsheet_id: str,
    service,
    row_number: int,
    content: str,
    status: str,
    error: str,
) -> None:
    """Update only the content/status/error cells for a single data row.

    The ``row_number`` is 1-based and matches the Google Sheet row number
    (including the header row). Only the ``content``, ``status``, and
    ``error`` columns are written; ``title`` and ``description`` are left
    untouched.
    """
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet.get('sheets', [])
        if not sheets:
            raise GoogleSheetsError("The spreadsheet contains no sheets.")
        first_sheet_title = sheets[0]['properties']['title']
    except HttpError as exc:
        if exc.resp.status == 404:
            raise SpreadsheetNotFoundError(
                f"Spreadsheet not found for ID '{spreadsheet_id}'."
            ) from exc
        elif exc.resp.status in (401, 403):
            raise SpreadsheetPermissionError(
                f"Permission denied accessing spreadsheet '{spreadsheet_id}'."
            ) from exc
        else:
            raise GoogleAPIError(f"Google Sheets API error: {exc.reason}") from exc
    except Exception as exc:
        if isinstance(exc, GoogleSheetsError):
            raise
        raise GoogleAPIError(f"Failed to retrieve spreadsheet metadata: {exc}") from exc

    range_name = f"'{first_sheet_title}'!A1:Z1"
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name,
        ).execute()
    except Exception as exc:
        raise GoogleAPIError(f"Failed to read header row: {exc}") from exc

    values = result.get('values', [[]])
    headers = values[0] if values else []
    normalised = [str(h).strip().lower() if h else '' for h in headers]
    header_indices = {name: idx for idx, name in enumerate(normalised) if name}

    required = ['content', 'status', 'error']
    missing = [h for h in required if h not in header_indices]
    if missing:
        raise GoogleSheetsError(
            f"The sheet is missing required result columns: {', '.join(missing)}. "
            "Call ensure_result_columns first."
        )

    update_values = []
    for col_name in required:
        idx = header_indices[col_name]
        value = {
            'content': content,
            'status': status,
            'error': error,
        }[col_name]
        update_values.append({
            'range': f"'{first_sheet_title}'!{_column_letter(idx)}{row_number}",
            'values': [[value]],
        })

    try:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                'valueInputOption': 'RAW',
                'data': update_values,
            },
        ).execute()
    except HttpError as exc:
        raise GoogleAPIError(
            f"Google Sheets API returned an error while updating row {row_number}: {exc.reason}"
        ) from exc
    except Exception as exc:
        raise GoogleAPIError(f"Failed to update row {row_number}: {exc}") from exc
