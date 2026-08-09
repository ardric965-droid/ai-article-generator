from django.utils import timezone

from generator.models import ArticleResult, GenerationJob
from generator.services.llm_service import (
    LLMConfigurationError,
    LLMRequestError,
    generate_article,
)
from generator.services.output_service import write_combined_output


def _determine_job_status(completed_rows: int, failed_rows: int) -> str:
    if completed_rows > 0 and failed_rows == 0:
        return GenerationJob.Status.COMPLETED
    if completed_rows > 0 and failed_rows > 0:
        return GenerationJob.Status.PARTIAL
    return GenerationJob.Status.FAILED


def _process_article(article: ArticleResult) -> None:
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
    """Process all pending articles for a job and write the combined TXT output."""
    job = GenerationJob.objects.prefetch_related('articles').get(pk=job_id)

    job.status = GenerationJob.Status.PROCESSING
    job.save(update_fields=['status'])

    pending_articles = job.articles.filter(
        status=ArticleResult.Status.PENDING,
    ).order_by('row_number')

    for article in pending_articles:
        current_status = GenerationJob.objects.values_list('status', flat=True).get(pk=job.pk)
        if current_status == GenerationJob.Status.CANCELLED:
            break
        _process_article(article)

    # Re-fetch articles directly from DB to bypass prefetched cache
    articles = list(ArticleResult.objects.filter(job_id=job.pk).order_by('row_number'))
    output_path = write_combined_output(
        articles,
        filename=f'job_{job.pk}_articles.txt',
    )

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
    job.output_file = output_path.name
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
            'output_file',
            'completed_at',
            'status',
        ],
    )

    return job
