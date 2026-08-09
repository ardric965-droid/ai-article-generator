import json
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from generator.models import ArticleResult, GenerationJob


class JobStatusApiTests(TestCase):
    def setUp(self):
        self.job = GenerationJob.objects.create(
            uploaded_file=SimpleUploadedFile('test.csv', b'title,description\n'),
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
        self.assertFalse(data['output_available'])

        articles = data['articles']
        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]['row_number'], 1)
        self.assertEqual(articles[0]['title'], 'Exercise Benefits')
        self.assertEqual(articles[0]['status'], 'completed')
        self.assertEqual(articles[0]['status_display'], 'Completed')

        self.assertEqual(articles[1]['row_number'], 2)
        self.assertEqual(articles[1]['title'], 'Saving Money')
        self.assertEqual(articles[1]['status'], 'pending')
        self.assertEqual(articles[1]['status_display'], 'Pending')

    def test_status_api_not_found(self):
        url = reverse('job_status_api', kwargs={'job_id': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class UploadCsvTests(TestCase):
    @patch('generator.views.process_job')
    @patch('generator.views.threading.Thread')
    def test_upload_csv_launches_background_thread(self, mock_thread, mock_process_job):
        csv_content = b'title,description\nTest Title,Test Description\n'
        uploaded_file = SimpleUploadedFile('test.csv', csv_content, content_type='text/csv')

        url = reverse('upload_csv')
        response = self.client.post(url, {'csv_file': uploaded_file})

        # Should redirect to job status
        job = GenerationJob.objects.first()
        self.assertIsNotNone(job)
        self.assertRedirects(response, reverse('job_status', kwargs={'job_id': job.pk}))

        # Assert a thread was instantiated and started
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
