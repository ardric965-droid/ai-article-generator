from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from generator.models import ArticleResult, GenerationJob
from generator.services.google_sheets_output_service import (
    OUTPUT_COLUMNS,
    OutputSheetCreationError,
    OutputSheetShareError,
    OutputSheetWriteError,
    build_spreadsheet_url,
    create_and_populate_output_sheet,
    create_output_spreadsheet,
    share_sheet_with_user,
    write_results_to_sheet,
)

SERVICE_MODULE = 'generator.services.google_sheets_output_service'


def _make_article(job, **overrides):
    defaults = {
        'row_number': 2,
        'title': 'Exercise Benefits',
        'description': 'Fitness info',
    }
    defaults.update(overrides)
    return ArticleResult.objects.create(job=job, **defaults)


class CreateOutputSpreadsheetTests(TestCase):
    @patch(f'{SERVICE_MODULE}.get_google_sheets_service')
    def test_create_returns_spreadsheet_id(self, mock_get_service):
        mock_get_service.return_value.spreadsheets.return_value.create.return_value \
            .execute.return_value = {'spreadsheetId': 'sheet-123'}

        spreadsheet_id = create_output_spreadsheet(title='My Output')

        self.assertEqual(spreadsheet_id, 'sheet-123')
        body = mock_get_service.return_value.spreadsheets.return_value.create \
            .call_args.kwargs['body']
        self.assertEqual(body['properties']['title'], 'My Output')

    @patch(f'{SERVICE_MODULE}.get_google_sheets_service')
    def test_create_uses_default_title_when_omitted(self, mock_get_service):
        mock_get_service.return_value.spreadsheets.return_value.create.return_value \
            .execute.return_value = {'spreadsheetId': 'sheet-123'}

        create_output_spreadsheet()

        body = mock_get_service.return_value.spreadsheets.return_value.create \
            .call_args.kwargs['body']
        self.assertIn('AI Articles', body['properties']['title'])

    @patch(f'{SERVICE_MODULE}.get_google_sheets_service')
    def test_create_raises_when_id_missing(self, mock_get_service):
        mock_get_service.return_value.spreadsheets.return_value.create.return_value \
            .execute.return_value = {}

        with self.assertRaises(OutputSheetCreationError):
            create_output_spreadsheet(title='My Output')
class WriteResultsToSheetTests(TestCase):
    def setUp(self):
        self.job = GenerationJob.objects.create(
            uploaded_file=SimpleUploadedFile('test.csv', b'title,description\n'),
        )
        self.article = _make_article(
            self.job,
            article='Exercise is good for you.',
            status=ArticleResult.Status.COMPLETED,
        )

    @patch(f'{SERVICE_MODULE}.get_google_sheets_service')
    def test_writes_headers_and_one_row_per_article(self, mock_get_service):
        mock_service = mock_get_service.return_value
        mock_service.spreadsheets.return_value.get.return_value.execute.return_value = {
            'sheets': [{'properties': {'title': 'Sheet1'}}],
        }
        mock_service.spreadsheets.return_value.values.return_value.update.return_value \
            .execute.return_value = {'updatedCells': 6}

        write_results_to_sheet('sheet-123', [self.article])

        update_call = mock_service.spreadsheets.return_value.values.return_value.update
        self.assertEqual(
            update_call.call_args.kwargs['range'],
            "'Sheet1'!A1",
        )
        body = update_call.call_args.kwargs['body']
        self.assertEqual(body['values'][0], OUTPUT_COLUMNS)
        self.assertEqual(body['values'][1], [
            'Exercise Benefits',
            'Fitness info',
            'Exercise is good for you.',
            'completed',
            '',
        ])

    @patch(f'{SERVICE_MODULE}.get_google_sheets_service')
    def test_rows_are_sorted_by_row_number(self, mock_get_service):
        mock_service = mock_get_service.return_value
        mock_service.spreadsheets.return_value.get.return_value.execute.return_value = {
            'sheets': [{'properties': {'title': 'Sheet1'}}],
        }
        second = _make_article(
            self.job,
            row_number=5,
            title='Saving Money',
            description='Financial tips',
            article='Save money wisely.',
            status=ArticleResult.Status.COMPLETED,
        )

        write_results_to_sheet('sheet-123', [second, self.article])

        body = mock_service.spreadsheets.return_value.values.return_value.update \
            .call_args.kwargs['body']
        self.assertEqual(body['values'][1][0], 'Exercise Benefits')
        self.assertEqual(body['values'][2][0], 'Saving Money')

    def test_empty_articles_raises(self):
        with self.assertRaises(OutputSheetWriteError):
            write_results_to_sheet('sheet-123', [])


class ShareSheetWithUserTests(TestCase):
    @patch(f'{SERVICE_MODULE}._get_drive_service')
    def test_share_grants_editor_permission(self, mock_get_drive):
        mock_get_drive.return_value.permissions.return_value.create.return_value \
            .execute.return_value = {'id': 'perm-1'}

        share_sheet_with_user('sheet-123', 'user@example.com')

        call = mock_get_drive.return_value.permissions.return_value.create
        self.assertEqual(call.call_args.kwargs['fileId'], 'sheet-123')
        self.assertEqual(call.call_args.kwargs['body'], {
            'type': 'user',
            'role': 'writer',
            'emailAddress': 'user@example.com',
        })
        self.assertFalse(call.call_args.kwargs.get('sendNotificationEmail'))

    def test_missing_email_raises(self):
        for bad_email in ('', '   '):
            with self.subTest(email=bad_email):
                with self.assertRaises(OutputSheetShareError):
                    share_sheet_with_user('sheet-123', bad_email)


class BuildSpreadsheetUrlTests(TestCase):
    def test_builds_shareable_url(self):
        self.assertEqual(
            build_spreadsheet_url('sheet-123'),
            'https://docs.google.com/spreadsheets/d/sheet-123/edit',
        )


class CreateAndPopulateOutputSheetTests(TestCase):
    @patch(f'{SERVICE_MODULE}.build_spreadsheet_url')
    @patch(f'{SERVICE_MODULE}.share_sheet_with_user')
    @patch(f'{SERVICE_MODULE}.write_results_to_sheet')
    @patch(f'{SERVICE_MODULE}.create_output_spreadsheet')
    def test_orchestrates_all_steps_and_returns_url(
        self,
        mock_create,
        mock_write,
        mock_share,
        mock_build_url,
    ):
        mock_create.return_value = 'sheet-123'
        expected_url = 'https://docs.google.com/spreadsheets/d/sheet-123/edit'
        mock_build_url.return_value = expected_url

        url = create_and_populate_output_sheet(
            [],
            'user@example.com',
            spreadsheet_title='My Title',
        )

        mock_create.assert_called_once_with(title='My Title')
        mock_write.assert_called_once_with('sheet-123', [])
        mock_share.assert_called_once_with('sheet-123', 'user@example.com')
        mock_build_url.assert_called_once_with('sheet-123')
        self.assertEqual(url, expected_url)

    @patch(f'{SERVICE_MODULE}.share_sheet_with_user')
    @patch(f'{SERVICE_MODULE}.write_results_to_sheet')
    @patch(f'{SERVICE_MODULE}.create_output_spreadsheet')
    def test_write_failure_propagates(self, mock_create, mock_write, mock_share):
        mock_create.return_value = 'sheet-123'
        mock_write.side_effect = OutputSheetWriteError('boom')

        with self.assertRaises(OutputSheetWriteError):
            create_and_populate_output_sheet([], 'user@example.com')

        mock_share.assert_not_called()

    @patch(f'{SERVICE_MODULE}.get_google_sheets_service')
    def test_create_wraps_api_failures(self, mock_get_service):
        mock_get_service.return_value.spreadsheets.return_value.create.return_value \
            .execute.side_effect = Exception('Network error')

        with self.assertRaises(OutputSheetCreationError):
            create_output_spreadsheet(title='My Output')