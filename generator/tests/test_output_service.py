import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from generator.models import ArticleResult, GenerationJob
from generator.services.output_service import write_combined_output


class WriteCombinedOutputTests(TestCase):
    def setUp(self):
        self.outputs_dir = Path(tempfile.mkdtemp())
        self.settings_override = self.settings(OUTPUTS_DIR=self.outputs_dir)
        self.settings_override.enable()

        self.job = GenerationJob.objects.create(
            uploaded_file=SimpleUploadedFile(
                'rows.csv',
                b'title,description\n',
            ),
        )

    def tearDown(self):
        self.settings_override.disable()

    def test_writes_combined_txt_file_with_articles_and_errors(self):
        successful = ArticleResult.objects.create(
            job=self.job,
            row_number=1,
            title='Benefits of Exercise',
            description='Why exercise helps.',
            article='Generated article text about exercise.',
            status=ArticleResult.Status.COMPLETED,
        )
        successful_second = ArticleResult.objects.create(
            job=self.job,
            row_number=2,
            title='Saving Money',
            description='Tips for saving.',
            article='Generated article text about saving money.',
            status=ArticleResult.Status.COMPLETED,
        )
        failed = ArticleResult.objects.create(
            job=self.job,
            row_number=3,
            title='Broken Row',
            description='This row failed.',
            status=ArticleResult.Status.FAILED,
            error_message='LLM request timed out.',
        )

        output_path = write_combined_output(
            [successful, successful_second, failed],
            filename='combined_output.txt',
        )

        self.assertEqual(output_path, self.outputs_dir / 'combined_output.txt')
        self.assertTrue(output_path.exists())

        content = output_path.read_text(encoding='utf-8')

        self.assertIn(
            '============================================================\n'
            'ARTICLE 1\n'
            'TITLE: Benefits of Exercise\n'
            '============================================================\n\n'
            'Generated article text about exercise.',
            content,
        )
        self.assertIn(
            '============================================================\n'
            'ARTICLE 2\n'
            'TITLE: Saving Money\n'
            '============================================================\n\n'
            'Generated article text about saving money.',
            content,
        )
        self.assertIn(
            '============================================================\n'
            'ERRORS\n'
            '============================================================\n\n'
            'ROW 3\n'
            'TITLE: Broken Row\n'
            'ERROR: LLM request timed out.',
            content,
        )
