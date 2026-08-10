from django.conf import settings
from django.db import models


class GenerationJob(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        PARTIAL = 'partial', 'Partially completed'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    uploaded_file = models.FileField(upload_to='uploads/')
    output_sheet_url = models.URLField(
        blank=True,
        null=True,
        help_text='URL of the new Google Sheet with the generated articles, shared with the user.',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='generation_jobs',
        null=True,
        blank=True,
        help_text='The logged-in user who owns this job; used to share the output sheet.',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    total_rows = models.PositiveIntegerField(default=0)
    completed_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    spreadsheet_id = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        label = f'Job #{self.pk}' if self.pk else 'Job (unsaved)'
        return f'{label} — {self.get_status_display()} ({self.completed_rows}/{self.total_rows} rows)'


class ArticleResult(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Generating'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    job = models.ForeignKey(
        GenerationJob,
        on_delete=models.CASCADE,
        related_name='articles',
    )
    row_number = models.PositiveIntegerField()
    title = models.CharField(max_length=500)
    description = models.TextField()
    article = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error_message = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    sheet_row_number = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['row_number']
        constraints = [
            models.UniqueConstraint(
                fields=['job', 'row_number'],
                name='unique_article_row_per_job',
            ),
        ]

    def __str__(self):
        title_preview = self.title[:50] + '…' if len(self.title) > 50 else self.title
        return f'Row {self.row_number}: {title_preview} ({self.get_status_display()})'
