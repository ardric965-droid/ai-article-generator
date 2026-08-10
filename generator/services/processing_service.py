import logging

from django.utils import timezone

from generator.models import ArticleResult, GenerationJob
from generator.services.google_sheets_service import (
    ensure_output_columns,
    get_google_sheets_service,
    update_sheet_row,
)
from generator.services.llm_service import (
    LLMConfigurationError,
    LLMRequestError,
    generate_article,
)


logger = logging.getLogger(__name__)


def _determine_job_status(completed_rows: int, failed_rows: int) -> str:
    if completed_rows > 0 and failed_rows == 0:
        return GenerationJob.Status.COMPLETED
    if completed_rows > 0 and failed_rows > 0:
        return GenerationJob.Status.PARTIAL
    return GenerationJob.Status.FAILED


def _process_article(article: ArticleResult) -> None:
    """Generate one article and persist the outcome in the database.

    The result is written back to the same input Google Sheet under the
    ``content``, ``status``, and ``error`` columns.
    """
    article.attempts += 1
    article.status = ArticleResult.Status.PROCESSING
    article.save(update_fields=['attempts', 'status'])

    try:
        article_text = generate_article(article.title, article.description)
    except (LLMConfigurationError, LLMRequestError) as exc:
        article.status = ArticleResult.Status.FAILED
        article.error_message = str(exc)
        article.save(update_fields=['status', 'error_message'])
        return

    article.status = ArticleResult.Status.COMPLETED
    article.article = article_text
    article.error_message = ''
    article.save(update_fields=['status', 'article', 'error_message'])


def process_job(job_id: int) -> GenerationJob:
    """Process all pending articles and write the results back to the input
    Google Sheet under the ``content``, ``status``, and ``error`` columns.
    """
    job = GenerationJob.objects.prefetch_related('articles').get(pk=job_id)

    job.status = GenerationJob.Status.PROCESSING
    job.save(update_fields=['status'])

    service = get_google_sheets_service()
    try:
        ensure_output_columns(job.spreadsheet_id, service)
    except Exception as exc:
        logger.warning('Could not ensure output columns for job %s: %s', job.pk, exc)
        job.status = GenerationJob.Status.FAILED
        job.completed_rows = 0
        job.failed_rows = 0
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                'status',
                'completed_rows',
                'failed_rows',
                'completed_at',
            ],
        )
        return job

    pending_articles = job.articles.filter(
        status__in=[
            ArticleResult.Status.PENDING,
            ArticleResult.Status.FAILED,
        ],
    ).order_by('row_number')

    for article in pending_articles:
        current_status = GenerationJob.objects.values_list('status', flat=True).get(pk=job.pk)
        if current_status == GenerationJob.Status.CANCELLED:
            break
        _process_article(article)
        try:
            update_sheet_row(
                job.spreadsheet_id,
                service,
                article.row_number,
                article.article or '',
                article.status,
                article.error_message or '',
            )
        except Exception as exc:
            logger.warning('Could not update sheet for job %s row %s: %s', job.pk, article.row_number, exc)

    # Re-fetch articles directly from DB to bypass prefetched cache.
    completed_rows = ArticleResult.objects.filter(
        job_id=job.pk,
        status=ArticleResult.Status.COMPLETED,
    ).count()
    failed_rows = ArticleResult.objects.filter(
        job_id=job.pk,
        status=ArticleResult.Status.FAILED,
    ).count()

    job.completed_rows = completed_rows
    job.failed_rows = failed_rows
    job.completed_at = timezone.now()

    # Check if job was cancelled during processing
    current_status = GenerationJob.objects.values_list('status', flat=True).get(pk=job.pk)
    if current_status == GenerationJob.Status.CANCELLED:
        job.status = GenerationJob.Status.CANCELLED
    else:
        job.status = _determine_job_status(completed_rows, failed_rows)

    job.save(
        update_fields=[
            'completed_rows',
            'failed_rows',
            'completed_at',
            'status',
        ],
    )

    return job
