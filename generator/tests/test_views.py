import json
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from generator.models import ArticleResult, GenerationJob


class JobStatusApiTests(TestCase):
    def setUp(self):
        self.job = GenerationJob.objects.create(
            total_rows=2,
            status=GenerationJob.Status.PROCESSING,
            completed_rows=1,
            failed_rows=0,
        )
        self.article1 = ArticleResult.objects.create(
            job=self.job,
            row_number=1,
            title='Exercise Benefits',
            description='Fitness info',
            article='Exercise is good.',
            status=ArticleResult.Status.COMPLETED,
        )
        self.article2 = ArticleResult.objects.create(
            job=self.job,
            row_number=2,
            title='Saving Money',
            description='Financial tips',
            status=ArticleResult.Status.PENDING,
        )

    def test_status_api_requires_login(self):
        url = reverse('job_status_api', kwargs={'job_id': self.job.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)


class AuthenticatedJobStatusApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', email='tester@example.com', password='testpass123')
        self.client.login(username='tester', password='testpass123')
        self.job = GenerationJob.objects.create(
            total_rows=2,
            status=GenerationJob.Status.PROCESSING,
            completed_rows=1,
            failed_rows=0,
        )
        self.article1 = ArticleResult.objects.create(
            job=self.job,
            row_number=2,
            title='Exercise Benefits',
            description='Fitness info',
            article='Exercise is good.',
            status=ArticleResult.Status.COMPLETED,
        )
        self.article2 = ArticleResult.objects.create(
            job=self.job,
            row_number=3,
            title='Saving Money',
            description='Financial tips',
            status=ArticleResult.Status.PENDING,
        )

    def test_status_api_returns_correct_json(self):
        url = reverse('job_status_api', kwargs={'job_id': self.job.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(data['status'], 'processing')
        self.assertEqual(data['status_display'], 'Processing')
        self.assertEqual(data['completed_rows'], 1)
        self.assertEqual(data['failed_rows'], 0)
        self.assertEqual(data['total_rows'], 2)
        self.assertEqual(data['progress'], 50)
        self.assertEqual(data['progress_text'], '1/2 rows processed')
        self.assertEqual(data['spreadsheet_id'], '')
        self.assertFalse(data['is_complete'])

        articles = data['articles']
        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]['row_number'], 2)
        self.assertEqual(articles[0]['data_row_index'], 1)
        self.assertEqual(articles[0]['title'], 'Exercise Benefits')
        self.assertEqual(articles[0]['status'], 'completed')
        self.assertEqual(articles[0]['status_display'], 'Completed')

        self.assertEqual(articles[1]['row_number'], 3)
        self.assertEqual(articles[1]['data_row_index'], 2)
        self.assertEqual(articles[1]['title'], 'Saving Money')
        self.assertEqual(articles[1]['status'], 'pending')
        self.assertEqual(articles[1]['status_display'], 'Pending')

    def test_status_api_includes_spreadsheet_id_when_set(self):
        self.job.spreadsheet_id = 'abc123'
        self.job.save(update_fields=['spreadsheet_id'])

        url = reverse('job_status_api', kwargs={'job_id': self.job.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['spreadsheet_id'], 'abc123')

    def test_status_api_includes_data_row_index(self):
        url = reverse('job_status_api', kwargs={'job_id': self.job.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        articles = data['articles']
        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]['row_number'], 2)
        self.assertEqual(articles[0]['data_row_index'], 1)
        self.assertEqual(articles[1]['row_number'], 3)
        self.assertEqual(articles[1]['data_row_index'], 2)

    def test_status_api_not_found(self):
        url = reverse('job_status_api', kwargs={'job_id': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_status_api_does_not_return_error_message_field(self):
        url = reverse('job_status_api', kwargs={'job_id': self.job.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertNotIn('error_message', data)


class AuthenticatedMissingJobTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', email='tester@example.com', password='testpass123')
        self.client.login(username='tester', password='testpass123')

    def test_status_api_not_found_for_authenticated_user(self):
        url = reverse('job_status_api', kwargs={'job_id': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class UploadGoogleSheetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', email='tester@example.com', password='testpass123')
        self.client.login(username='tester', password='testpass123')

    @patch('generator.views.process_job')
    @patch('generator.views.threading.Thread')
    @patch('generator.views.read_sheet_rows')
    @patch('generator.views.validate_sheet_connection')
    def test_upload_google_sheet_launches_background_thread(self, mock_validate, mock_read_rows, mock_thread, mock_process_job):
        mock_validate.return_value = 'sheet-id-123'
        mock_read_rows.return_value = [
            {'row_number': 2, 'title': 'Test Title', 'description': 'Test Description'},
        ]

        url = reverse('upload_spreadsheet')
        response = self.client.post(url, {'spreadsheet_url': 'https://docs.google.com/spreadsheets/d/sheet-id-123/edit'})

        job = GenerationJob.objects.first()
        self.assertIsNotNone(job)
        self.assertEqual(job.user, self.user)
        self.assertEqual(job.spreadsheet_id, 'sheet-id-123')
        self.assertEqual(job.total_rows, 1)
        self.assertRedirects(response, reverse('job_status', kwargs={'job_id': job.pk}))

        article = job.articles.get(row_number=2)
        self.assertEqual(article.title, 'Test Title')
        self.assertEqual(article.description, 'Test Description')

        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    def test_upload_google_sheet_rejects_invalid_sheet_reference(self):
        url = reverse('upload_spreadsheet')
        response = self.client.post(url, {'spreadsheet_url': 'not-a-sheet-link'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter a valid Google Sheets URL or spreadsheet ID.')
        self.assertEqual(GenerationJob.objects.count(), 0)


class AnonymousAccessTests(TestCase):
    def test_upload_redirects_to_login(self):
        response = self.client.get(reverse('upload_spreadsheet'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_job_status_redirects_to_login(self):
        response = self.client.get(reverse('job_status', kwargs={'job_id': 1}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)


class JobStatusPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='tester',
            email='tester@example.com',
            password='testpass123',
        )
        self.client.login(username='tester', password='testpass123')
        self.job = GenerationJob.objects.create(
            total_rows=1,
            status=GenerationJob.Status.COMPLETED,
        )

    def test_status_page_shows_write_back_message(self):
        url = reverse('job_status', kwargs={'job_id': self.job.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'written back to your original Google Sheet')
        self.assertContains(response, 'content')
        self.assertContains(response, 'status')
        self.assertContains(response, 'error')

    def test_completed_job_with_spreadsheet_id_shows_open_sheet_link(self):
        self.job.status = GenerationJob.Status.COMPLETED
        self.job.spreadsheet_id = 'abc123'
        self.job.save(update_fields=['status', 'spreadsheet_id'])

        url = reverse('job_status', kwargs={'job_id': self.job.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Open your Google Sheet')
        self.assertContains(response, 'https://docs.google.com/spreadsheets/d/abc123/edit')
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')

    def test_completed_job_without_spreadsheet_id_does_not_show_link(self):
        self.job.status = GenerationJob.Status.COMPLETED
        self.job.save(update_fields=['status'])

        url = reverse('job_status', kwargs={'job_id': self.job.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Open your Google Sheet')

    def test_processing_job_with_spreadsheet_id_does_not_show_link(self):
        self.job.status = GenerationJob.Status.PROCESSING
        self.job.spreadsheet_id = 'abc123'
        self.job.save(update_fields=['status', 'spreadsheet_id'])

        url = reverse('job_status', kwargs={'job_id': self.job.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'https://docs.google.com/spreadsheets/d/abc123/edit')

    def test_status_page_shows_data_row_index_not_sheet_row(self):
        ArticleResult.objects.create(
            job=self.job,
            row_number=5,
            title='Row 5 Title',
            description='Desc',
            status=ArticleResult.Status.COMPLETED,
        )

        url = reverse('job_status', kwargs={'job_id': self.job.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<td>4</td>')
        self.assertNotContains(response, '<td>5</td>')
