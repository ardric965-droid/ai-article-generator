from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.test.utils import override_settings
from googleapiclient.errors import HttpError
import httplib2

from generator.services.google_sheets_service import (
    extract_spreadsheet_id,
    get_google_sheets_service,
    validate_sheet_connection,
    read_sheet_rows,
    classify_rows_for_job,
    InvalidSpreadsheetURLError,
    SpreadsheetNotFoundError,
    SpreadsheetPermissionError,
    GoogleAPIError,
    GoogleSheetsError,
)

class GoogleSheetsServiceTests(TestCase):
    def test_extract_spreadsheet_id_valid_urls(self):
        valid_urls = [
            "https://docs.google.com/spreadsheets/d/1aBcD_eFgHiJkLmNoPqRsTuVwXyZ1234567890ab/edit#gid=0",
            "https://docs.google.com/spreadsheets/d/1aBcD_eFgHiJkLmNoPqRsTuVwXyZ1234567890ab/edit?usp=sharing",
            "https://docs.google.com/spreadsheets/d/1aBcD_eFgHiJkLmNoPqRsTuVwXyZ1234567890ab/",
            "https://docs.google.com/spreadsheets/d/1aBcD_eFgHiJkLmNoPqRsTuVwXyZ1234567890ab",
        ]
        for url in valid_urls:
            with self.subTest(url=url):
                self.assertEqual(
                    extract_spreadsheet_id(url),
                    "1aBcD_eFgHiJkLmNoPqRsTuVwXyZ1234567890ab"
                )

    def test_extract_spreadsheet_id_valid_raw_id(self):
        raw_id = "1aBcD_eFgHiJkLmNoPqRsTuVwXyZ1234567890ab"
        self.assertEqual(extract_spreadsheet_id(raw_id), raw_id)

    def test_extract_spreadsheet_id_invalid(self):
        invalid_inputs = [
            "",
            "   ",
            "https://google.com",
            "https://docs.google.com/spreadsheets/d/",
            "invalid@character$",
        ]
        for val in invalid_inputs:
            with self.subTest(val=val):
                with self.assertRaises(InvalidSpreadsheetURLError):
                    extract_spreadsheet_id(val)

    @override_settings(GOOGLE_CREDENTIALS_FILE='/nonexistent/path/creds.json')
    def test_get_service_missing_file(self):
        with self.assertRaises(GoogleAPIError) as ctx:
            get_google_sheets_service()
        self.assertIn("Google credentials file not found", str(ctx.exception))

    @patch('os.path.exists', return_value=True)
    @patch('generator.services.google_sheets_service.service_account.Credentials.from_service_account_file')
    @patch('generator.services.google_sheets_service.build')
    @override_settings(GOOGLE_CREDENTIALS_FILE='/fake/path/creds.json')
    def test_get_service_success(self, mock_build, mock_from_file, mock_exists):
        mock_creds = MagicMock()
        mock_from_file.return_value = mock_creds
        
        get_google_sheets_service()
        
        mock_from_file.assert_called_once_with(
            '/fake/path/creds.json',
            scopes=['https://www.googleapis.com/auth/spreadsheets'],
        )
        mock_build.assert_called_once_with('sheets', 'v4', credentials=mock_creds, cache_discovery=False)

    @patch('os.path.exists', return_value=True)
    @patch('generator.services.google_sheets_service.service_account.Credentials.from_service_account_file')
    @override_settings(GOOGLE_CREDENTIALS_FILE='/fake/path/creds.json')
    def test_get_service_failure(self, mock_from_file, mock_exists):

        mock_from_file.side_effect = Exception("Auth failed")
        with self.assertRaises(GoogleAPIError) as ctx:
            get_google_sheets_service()
        self.assertIn("Failed to authenticate or initialize", str(ctx.exception))

    @patch('generator.services.google_sheets_service.get_google_sheets_service')
    def test_validate_connection_success(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_get_request = mock_service.spreadsheets.return_value.get.return_value
        mock_get_request.execute.return_value = {'spreadsheetId': '123'}

        url = "https://docs.google.com/spreadsheets/d/123/edit"
        result = validate_sheet_connection(url)
        self.assertEqual(result, '123')
        mock_service.spreadsheets.return_value.get.assert_called_once_with(
            spreadsheetId='123',
            fields='spreadsheetId'
        )

    @patch('generator.services.google_sheets_service.get_google_sheets_service')
    def test_validate_connection_not_found(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_get_request = mock_service.spreadsheets.return_value.get.return_value
        
        resp = httplib2.Response({'status': 404})
        mock_get_request.execute.side_effect = HttpError(resp, b'Not Found')

        url = "https://docs.google.com/spreadsheets/d/123/edit"
        with self.assertRaises(SpreadsheetNotFoundError):
            validate_sheet_connection(url)

    @patch('generator.services.google_sheets_service.get_google_sheets_service')
    def test_validate_connection_permission_denied(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_get_request = mock_service.spreadsheets.return_value.get.return_value
        
        resp = httplib2.Response({'status': 403})
        mock_get_request.execute.side_effect = HttpError(resp, b'Forbidden')

        url = "https://docs.google.com/spreadsheets/d/123/edit"
        with self.assertRaises(SpreadsheetPermissionError):
            validate_sheet_connection(url)

    @patch('generator.services.google_sheets_service.get_google_sheets_service')
    def test_validate_connection_other_api_error(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_get_request = mock_service.spreadsheets.return_value.get.return_value
        
        resp = httplib2.Response({'status': 500})
        mock_get_request.execute.side_effect = HttpError(resp, b'Internal Server Error')

        url = "https://docs.google.com/spreadsheets/d/123/edit"
        with self.assertRaises(GoogleAPIError) as ctx:
            validate_sheet_connection(url)
        self.assertIn("Google Sheets API returned an error", str(ctx.exception))

    @patch('generator.services.google_sheets_service.get_google_sheets_service')
    def test_validate_connection_unexpected_error(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_get_request = mock_service.spreadsheets.return_value.get.return_value
        mock_get_request.execute.side_effect = Exception("Network loss")

        url = "https://docs.google.com/spreadsheets/d/123/edit"
        with self.assertRaises(GoogleAPIError) as ctx:
            validate_sheet_connection(url)
        self.assertIn("An unexpected error occurred", str(ctx.exception))

    @patch('generator.services.google_sheets_service.get_google_sheets_service')
    def test_read_sheet_rows_success(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        
        mock_get_meta = mock_service.spreadsheets.return_value.get.return_value
        mock_get_meta.execute.return_value = {
            'sheets': [{'properties': {'title': 'ArticlesSheet'}}]
        }
        
        mock_get_values = mock_service.spreadsheets.return_value.values.return_value.get.return_value
        mock_get_values.execute.return_value = {
            'values': [
                ['title', 'description', 'content', 'status', 'error'],
                ['Exercising', 'Improve health.'],
                ['Saving', 'Personal finance.']
            ]
        }
        
        result = read_sheet_rows('dummy-id')
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], {
            'row_number': 2,
            'title': 'Exercising',
            'description': 'Improve health.',
            'status': '',
            'content': '',
            'error': '',
        })
        self.assertEqual(result[1], {
            'row_number': 3,
            'title': 'Saving',
            'description': 'Personal finance.',
            'status': '',
            'content': '',
            'error': '',
        })
        
        mock_service.spreadsheets.return_value.get.assert_called_once_with(
            spreadsheetId='dummy-id'
        )
        mock_service.spreadsheets.return_value.values.return_value.get.assert_called_once_with(
            spreadsheetId='dummy-id',
            range="'ArticlesSheet'!A:Z"
        )
        
    @patch('generator.services.google_sheets_service.get_google_sheets_service')
    def test_read_sheet_rows_auto_creates_missing_headers(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        
        mock_get_meta = mock_service.spreadsheets.return_value.get.return_value
        mock_get_meta.execute.return_value = {
            'sheets': [{'properties': {'title': 'Sheet1'}}]
        }
        
        mock_get_values = mock_service.spreadsheets.return_value.values.return_value.get.return_value
        mock_get_values.execute.return_value = {
            'values': [
                ['title', 'description'],
                ['Title 1', 'Desc 1']
            ]
        }
        
        
        result = read_sheet_rows('dummy-id')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['title'], 'Title 1')
        

    @patch('generator.services.google_sheets_service.get_google_sheets_service')
    def test_read_sheet_rows_empty_sheet(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        
        mock_get_meta = mock_service.spreadsheets.return_value.get.return_value
        mock_get_meta.execute.return_value = {
            'sheets': [{'properties': {'title': 'Sheet1'}}]
        }
        
        mock_get_values = mock_service.spreadsheets.return_value.values.return_value.get.return_value
        mock_get_values.execute.return_value = {}
        
        with self.assertRaises(GoogleSheetsError) as ctx:
            read_sheet_rows('dummy-id')
        self.assertIn("sheet is empty", str(ctx.exception))

    @patch('generator.services.google_sheets_service.get_google_sheets_service')
    def test_read_sheet_rows_missing_header_row(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        
        mock_get_meta = mock_service.spreadsheets.return_value.get.return_value
        mock_get_meta.execute.return_value = {
            'sheets': [{'properties': {'title': 'Sheet1'}}]
        }
        
        mock_get_values = mock_service.spreadsheets.return_value.values.return_value.get.return_value
        mock_get_values.execute.return_value = {'values': [['', '   ']]}
        
        with self.assertRaises(GoogleSheetsError) as ctx:
            read_sheet_rows('dummy-id')
        self.assertIn("must include a header row", str(ctx.exception))

    @patch('generator.services.google_sheets_service.get_google_sheets_service')
    def test_read_sheet_rows_missing_required_columns(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        
        mock_get_meta = mock_service.spreadsheets.return_value.get.return_value
        mock_get_meta.execute.return_value = {
            'sheets': [{'properties': {'title': 'Sheet1'}}]
        }
        
        mock_get_values = mock_service.spreadsheets.return_value.values.return_value.get.return_value
        mock_get_values.execute.return_value = {
            'values': [
                ['title', 'wrong_column'],
                ['Title 1', 'Desc 1']
            ]
        }
        
        with self.assertRaises(GoogleSheetsError) as ctx:
            read_sheet_rows('dummy-id')
        self.assertIn("must include 'title' and 'description' columns", str(ctx.exception))

    @patch('generator.services.google_sheets_service.get_google_sheets_service')
    def test_read_sheet_rows_empty_values_validation(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        
        mock_get_meta = mock_service.spreadsheets.return_value.get.return_value
        mock_get_meta.execute.return_value = {
            'sheets': [{'properties': {'title': 'Sheet1'}}]
        }
        
        mock_get_values = mock_service.spreadsheets.return_value.values.return_value.get.return_value
        mock_get_values.execute.return_value = {
            'values': [
                ['title', 'description'],
                ['Title 1', '']
            ]
        }
        
        with self.assertRaises(GoogleSheetsError) as ctx:
            read_sheet_rows('dummy-id')
        self.assertIn("Row 2: description must not be empty", str(ctx.exception))


class ClassifyRowsForJobTests(TestCase):
    def test_all_pending_rows(self):
        rows = [
            {'row_number': 2, 'title': 'T1', 'description': 'D1', 'status': '', 'content': '', 'error': ''},
            {'row_number': 3, 'title': 'T2', 'description': 'D2', 'status': 'pending', 'content': '', 'error': ''},
        ]
        result = classify_rows_for_job(rows)
        self.assertFalse(result['all_completed'])
        self.assertEqual(result['completed_count'], 0)
        self.assertEqual(result['pending_count'], 2)
        self.assertEqual(len(result['pending_rows']), 2)
        self.assertEqual(len(result['completed_rows']), 0)

    def test_completed_without_content_treated_as_pending(self):
        # A 'completed' status with empty content is treated as pending
        # because it indicates a previous incomplete write-back.
        row = {'row_number': 2, 'title': 'T1', 'description': 'D1', 'status': 'completed', 'content': '', 'error': ''}
        result = classify_rows_for_job([row])
        self.assertFalse(result['all_completed'])
        self.assertEqual(result['completed_count'], 0)
        self.assertEqual(result['pending_count'], 1)
        self.assertIn(row, result['pending_rows'])

    def test_mixed_rows_case_and_space_insensitive(self):
        rows = [
            {'row_number': 2, 'title': 'T1', 'description': 'D1', 'status': '  Completed  ', 'content': 'Body one', 'error': ''},
            {'row_number': 3, 'title': 'T2', 'description': 'D2', 'status': 'COMPLETED', 'content': 'Body two', 'error': ''},
            {'row_number': 4, 'title': 'T3', 'description': 'D3', 'status': 'failed', 'content': '', 'error': 'boom'},
            {'row_number': 5, 'title': 'T4', 'description': 'D4', 'status': '', 'content': '', 'error': ''},
        ]
        result = classify_rows_for_job(rows)
        self.assertFalse(result['all_completed'])
        self.assertEqual(result['completed_count'], 2)
        self.assertEqual(result['pending_count'], 2)
        self.assertEqual([r['row_number'] for r in result['completed_rows']], [2, 3])
        self.assertEqual([r['row_number'] for r in result['pending_rows']], [4, 5])

    def test_all_completed(self):
        rows = [
            {'row_number': 2, 'title': 'T1', 'description': 'D1', 'status': 'completed', 'content': 'Body', 'error': ''},
            {'row_number': 3, 'title': 'T2', 'description': 'D2', 'status': 'completed', 'content': 'Body', 'error': ''},
        ]
        result = classify_rows_for_job(rows)
        self.assertTrue(result['all_completed'])
        self.assertEqual(result['completed_count'], 2)
        self.assertEqual(result['pending_count'], 0)
        self.assertEqual(len(result['completed_rows']), 2)
        self.assertEqual(len(result['pending_rows']), 0)

    def test_no_rows(self):
        result = classify_rows_for_job([])
        self.assertFalse(result['all_completed'])
        self.assertEqual(result['completed_count'], 0)
        self.assertEqual(result['pending_count'], 0)
