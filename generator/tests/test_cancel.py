from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from generator.models import ArticleResult, GenerationJob
from generator.services.processing_service import process_job




class CancelJobViewTests(TestCase):
    def setUp(self):
        # Stop/resume views are @login_required, so authenticate the client.
        self.user = User.objects.create_user(
            username='tester',
            password='testpass123',
        )
        self.client.login(username='tester', password='testpass123')
        self.job = GenerationJob.objects.create(
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

    @patch('generator.views.threading.Thread')
    def test_resume_job_endpoint_restarts_cancelled_job(self, mock_thread):
        self.job.status = GenerationJob.Status.CANCELLED
        self.job.save(update_fields=['status'])

        url = reverse('resume_job', kwargs={'job_id': self.job.pk})
        response = self.client.post(url)

        self.job.refresh_from_db()
        self.assertRedirects(response, reverse('job_status', kwargs={'job_id': self.job.pk}))
        self.assertEqual(self.job.status, GenerationJob.Status.PENDING)
        mock_thread.assert_called_once()


class CancelJobProcessingTests(TestCase):
    def setUp(self):
        self.job = GenerationJob.objects.create(
            total_rows=3,
            status=GenerationJob.Status.PENDING,
            spreadsheet_id='sheet-id-123',
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

    @patch('generator.services.processing_service.update_sheet_row')
    @patch('generator.services.processing_service.ensure_result_columns')
    @patch('generator.services.processing_service.generate_article')
    def test_process_job_stops_when_cancelled_midway(
        self,
        mock_generate,
        mock_ensure_columns,
        mock_update_row,
    ):
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

        mock_ensure_columns.assert_called_once()
        self.assertEqual(mock_update_row.call_count, 1)

    @patch('generator.services.processing_service.update_sheet_row')
    @patch('generator.services.processing_service.ensure_result_columns')
    @patch('generator.services.processing_service.generate_article')
    def test_process_job_resumes_from_pending_rows_only(
        self,
        mock_generate,
        mock_ensure_columns,
        mock_update_row,
    ):
        self.art1.status = ArticleResult.Status.COMPLETED
        self.art1.article = 'Already generated'
        self.art1.save(update_fields=['status', 'article'])

        self.job.status = GenerationJob.Status.CANCELLED
        self.job.save(update_fields=['status'])

        mock_generate.return_value = 'Generated later'

        processed_job = process_job(self.job.pk)

        self.assertEqual(processed_job.status, GenerationJob.Status.COMPLETED)
        self.assertEqual(processed_job.completed_rows, 3)
        self.assertEqual(processed_job.failed_rows, 0)

        self.art2.refresh_from_db()
        self.art3.refresh_from_db()
        self.assertEqual(self.art2.status, ArticleResult.Status.COMPLETED)
        self.assertEqual(self.art3.status, ArticleResult.Status.COMPLETED)
        self.assertEqual(mock_generate.call_count, 2)
        self.assertEqual(
            mock_generate.call_args_list[0].args,
            (self.art2.title, self.art2.description),
        )
        self.assertEqual(
            mock_generate.call_args_list[1].args,
            (self.art3.title, self.art3.description),
        )

        mock_ensure_columns.assert_called_once()
        self.assertEqual(mock_update_row.call_count, 2)


class AnonymousCancelAccessTests(TestCase):
    """Stop and resume must be login-protected like the other job views."""

    def setUp(self):
        self.job = GenerationJob.objects.create(
            total_rows=1,
            status=GenerationJob.Status.PROCESSING,
        )

    def test_stop_job_redirects_anonymous_user_to_login(self):
        url = reverse('stop_job', kwargs={'job_id': self.job.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

        # A logged-out user must not be able to cancel the job.
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, GenerationJob.Status.PROCESSING)

    def test_resume_job_redirects_anonymous_user_to_login(self):
        url = reverse('resume_job', kwargs={'job_id': self.job.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

        # A logged-out user must not be able to resume the job.
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, GenerationJob.Status.PROCESSING)
