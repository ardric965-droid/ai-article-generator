from pathlib import Path
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from generator.models import ArticleResult, GenerationJob
from generator.services.processing_service import process_job


class CancelJobViewTests(TestCase):
    def setUp(self):
        self.job = GenerationJob.objects.create(
            uploaded_file=SimpleUploadedFile('test.csv', b'title,description\n'),
            total_rows=1,
            status=GenerationJob.Status.PROCESSING,
        )

    def test_stop_job_endpoint_updates_status(self):
        url = reverse('stop_job', kwargs={'job_id': self.job.pk})
        response = self.client.post(url)
        
        # Verify it redirects to status view
        self.assertRedirects(response, reverse('job_status', kwargs={'job_id': self.job.pk}))
        
        # Verify job is cancelled
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, GenerationJob.Status.CANCELLED)

    def test_cannot_stop_completed_job(self):
        self.job.status = GenerationJob.Status.COMPLETED
        self.job.save(update_fields=['status'])

        url = reverse('stop_job', kwargs={'job_id': self.job.pk})
        response = self.client.post(url)
        
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, GenerationJob.Status.COMPLETED)


class CancelJobProcessingTests(TestCase):
    def setUp(self):
        self.outputs_dir = Path(tempfile.mkdtemp())
        self.settings_override = self.settings(OUTPUTS_DIR=self.outputs_dir)
        self.settings_override.enable()

        self.job = GenerationJob.objects.create(
            uploaded_file=SimpleUploadedFile('test.csv', b'title,description\n'),
            total_rows=3,
            status=GenerationJob.Status.PENDING,
        )
        self.art1 = ArticleResult.objects.create(
            job=self.job, row_number=1, title='Title 1', description='Desc 1'
        )
        self.art2 = ArticleResult.objects.create(
            job=self.job, row_number=2, title='Title 2', description='Desc 2'
        )
        self.art3 = ArticleResult.objects.create(
            job=self.job, row_number=3, title='Title 3', description='Desc 3'
        )

    def tearDown(self):
        self.settings_override.disable()

    @patch('generator.services.processing_service.generate_article')
    def test_process_job_stops_when_cancelled_midway(self, mock_generate):
        # We want to simulate the job being cancelled after the first row
        def side_effect(title, description):
            if title == 'Title 1':
                # Cancel job midway
                self.job.status = GenerationJob.Status.CANCELLED
                self.job.save(update_fields=['status'])
                return 'Article 1 Content'
            return 'Should not be called'

        mock_generate.side_effect = side_effect

        processed_job = process_job(self.job.pk)

        # The job should retain CANCELLED status
        self.assertEqual(processed_job.status, GenerationJob.Status.CANCELLED)
        self.assertEqual(processed_job.completed_rows, 1)
        self.assertEqual(processed_job.failed_rows, 0)
        
        # Verify first article is completed, second/third remain pending
        self.art1.refresh_from_db()
        self.art2.refresh_from_db()
        self.art3.refresh_from_db()
        
        self.assertEqual(self.art1.status, ArticleResult.Status.COMPLETED)
        self.assertEqual(self.art2.status, ArticleResult.Status.PENDING)
        self.assertEqual(self.art3.status, ArticleResult.Status.PENDING)

        # Verify output file generated so far
        self.assertTrue((self.outputs_dir / processed_job.output_file).exists())
        content = (self.outputs_dir / processed_job.output_file).read_text(encoding='utf-8')
        self.assertIn('Title 1', content)
        self.assertNotIn('Title 2', content)
