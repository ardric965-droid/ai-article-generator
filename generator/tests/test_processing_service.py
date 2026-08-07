import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from generator.models import ArticleResult, GenerationJob
from generator.services.llm_service import LLMRequestError
from generator.services.processing_service import process_job


class ProcessJobTests(TestCase):
    def setUp(self):
        self.outputs_dir = Path(tempfile.mkdtemp())
        self.settings_override = self.settings(OUTPUTS_DIR=self.outputs_dir)
        self.settings_override.enable()

        self.job = GenerationJob.objects.create(
            uploaded_file=SimpleUploadedFile(
                'rows.csv',
                b'title,description\n',
            ),
            total_rows=2,
            status=GenerationJob.Status.PENDING,
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

    def tearDown(self):
        self.settings_override.disable()

    @patch('generator.services.processing_service.generate_article')
    def test_process_job_saves_successful_articles_and_output(self, mock_generate):
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
        self.assertEqual(processed_job.output_file, f'job_{self.job.pk}_articles.txt')
        self.assertIsNotNone(processed_job.completed_at)
        self.assertEqual(self.first_article.status, ArticleResult.Status.COMPLETED)
        self.assertEqual(self.first_article.attempts, 1)
        self.assertEqual(self.first_article.article, 'Generated exercise article.')
        self.assertTrue((self.outputs_dir / processed_job.output_file).exists())

    @patch('generator.services.processing_service.generate_article')
    def test_process_job_continues_after_row_failure(self, mock_generate):
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

        content = (self.outputs_dir / processed_job.output_file).read_text(
            encoding='utf-8',
        )
        self.assertIn('Generated exercise article.', content)
        self.assertIn('ERROR: Temporary outage', content)
