from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from generator.models import ArticleResult, GenerationJob
from generator.services.llm_service import LLMRequestError
from generator.services.processing_service import process_job


class ProcessJobTests(TestCase):
    def setUp(self):
        self.job = GenerationJob.objects.create(
            uploaded_file=SimpleUploadedFile(
                'rows.csv',
                b'title,description\n',
            ),
            total_rows=2,
            status=GenerationJob.Status.PENDING,
            spreadsheet_id='sheet-id-123',
        )
        self.first_article = ArticleResult.objects.create(
            job=self.job,
            row_number=1,
            title='Benefits of Exercise',
            description='Why exercise helps.',
        )
        self.second_article = ArticleResult.objects.create(
            job=self.job,
            row_number=2,
            title='Saving Money',
            description='Tips for saving.',
        )

    @patch('generator.services.processing_service.generate_article')
    @patch('generator.services.processing_service.update_sheet_row')
    @patch('generator.services.processing_service.ensure_output_columns')
    def test_process_job_saves_successful_articles_and_writes_back(
        self,
        mock_ensure_columns,
        mock_update_row,
        mock_generate,
    ):
        mock_generate.side_effect = [
            'Generated exercise article.',
            'Generated savings article.',
        ]

        processed_job = process_job(self.job.pk)

        self.first_article.refresh_from_db()
        self.second_article.refresh_from_db()

        self.assertEqual(processed_job.status, GenerationJob.Status.COMPLETED)
        self.assertEqual(processed_job.completed_rows, 2)
        self.assertEqual(processed_job.failed_rows, 0)
        self.assertIsNotNone(processed_job.completed_at)
        self.assertEqual(self.first_article.status, ArticleResult.Status.COMPLETED)
        self.assertEqual(self.first_article.attempts, 1)
        self.assertEqual(self.first_article.article, 'Generated exercise article.')

        mock_ensure_columns.assert_called_once()
        self.assertEqual(mock_ensure_columns.call_args[0][0], 'sheet-id-123')
        self.assertEqual(mock_update_row.call_count, 2)
        mock_update_row.assert_any_call(
            'sheet-id-123',
            mock_update_row.call_args[0][1],
            1,
            'Generated exercise article.',
            ArticleResult.Status.COMPLETED,
            '',
        )
        mock_update_row.assert_any_call(
            'sheet-id-123',
            mock_update_row.call_args[0][1],
            2,
            'Generated savings article.',
            ArticleResult.Status.COMPLETED,
            '',
        )

    @patch('generator.services.processing_service.generate_article')
    @patch('generator.services.processing_service.update_sheet_row')
    @patch('generator.services.processing_service.ensure_output_columns')
    def test_process_job_continues_after_row_failure(
        self,
        mock_ensure_columns,
        mock_update_row,
        mock_generate,
    ):
        mock_generate.side_effect = [
            'Generated exercise article.',
            LLMRequestError('Temporary outage'),
        ]

        processed_job = process_job(self.job.pk)

        self.first_article.refresh_from_db()
        self.second_article.refresh_from_db()

        self.assertEqual(processed_job.status, GenerationJob.Status.PARTIAL)
        self.assertEqual(processed_job.completed_rows, 1)
        self.assertEqual(processed_job.failed_rows, 1)
        self.assertEqual(self.first_article.status, ArticleResult.Status.COMPLETED)
        self.assertEqual(self.second_article.status, ArticleResult.Status.FAILED)
        self.assertEqual(self.second_article.error_message, 'Temporary outage')
        self.assertEqual(self.second_article.attempts, 1)

        mock_ensure_columns.assert_called_once()
        self.assertEqual(mock_ensure_columns.call_args[0][0], 'sheet-id-123')
        self.assertEqual(mock_update_row.call_count, 2)
        mock_update_row.assert_any_call(
            'sheet-id-123',
            mock_update_row.call_args[0][1],
            1,
            'Generated exercise article.',
            ArticleResult.Status.COMPLETED,
            '',
        )
        mock_update_row.assert_any_call(
            'sheet-id-123',
            mock_update_row.call_args[0][1],
            2,
            '',
            ArticleResult.Status.FAILED,
            'Temporary outage',
        )

    @patch('generator.services.processing_service.generate_article')
    @patch('generator.services.processing_service.update_sheet_row')
    @patch('generator.services.processing_service.ensure_output_columns')
    def test_process_job_ensures_output_columns_and_updates_rows(
        self,
        mock_ensure_columns,
        mock_update_row,
        mock_generate,
    ):
        mock_generate.side_effect = [
            'Generated exercise article.',
            'Generated savings article.',
        ]

        processed_job = process_job(self.job.pk)

        mock_ensure_columns.assert_called_once()
        self.assertEqual(mock_ensure_columns.call_args[0][0], 'sheet-id-123')
        self.assertEqual(mock_update_row.call_count, 2)
        self.assertIsNone(processed_job.output_sheet_url)
