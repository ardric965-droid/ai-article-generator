import threading

from django.contrib.auth.decorators import login_required
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from generator.forms import SpreadsheetUploadForm
from generator.models import ArticleResult, GenerationJob

try:
    from generator.services.google_sheets_service import read_sheet_rows, validate_sheet_connection
except ModuleNotFoundError:
    def read_sheet_rows(*args, **kwargs):
        raise RuntimeError('Google Sheets dependencies are not installed.')

    def validate_sheet_connection(*args, **kwargs):
        raise RuntimeError('Google Sheets dependencies are not installed.')

try:
    from generator.services.processing_service import process_job
except ModuleNotFoundError:
    def process_job(*args, **kwargs):
        raise RuntimeError('Processing dependencies are not installed.')


def _run_async_job(job_id: int):
    try:
        process_job(job_id)
    finally:
        close_old_connections()


@login_required
def upload_csv(request):
    if request.method == 'POST':
        form = SpreadsheetUploadForm(request.POST)
        if form.is_valid():
            spreadsheet_url = form.cleaned_data['spreadsheet_url']
            try:
                spreadsheet_id = validate_sheet_connection(spreadsheet_url)
                rows = read_sheet_rows(spreadsheet_id)
            except Exception as exc:
                form.add_error('spreadsheet_url', str(exc))
            else:
                job = GenerationJob.objects.create(
                    uploaded_file=SimpleUploadedFile(
                        f'{spreadsheet_id}.txt',
                        b'',
                        content_type='text/plain',
                    ),
                    total_rows=len(rows),
                    status=GenerationJob.Status.PENDING,
                    spreadsheet_id=spreadsheet_id,
                    user=request.user,
                )
                ArticleResult.objects.bulk_create([
                    ArticleResult(
                        job=job,
                        row_number=row['row_number'],
                        title=row['title'],
                        description=row['description'],
                        sheet_row_number=row['row_number'],
                    )
                    for row in rows
                ])

                threading.Thread(target=_run_async_job, args=(job.pk,), daemon=True).start()

                return redirect('job_status', job_id=job.pk)
    else:
        form = SpreadsheetUploadForm()

    return render(request, 'generator/upload.html', {'form': form})


@login_required
def job_status_api(request, job_id):
    job = get_object_or_404(
        GenerationJob.objects.prefetch_related('articles'),
        pk=job_id,
    )
    articles_data = [
        {
            'row_number': article.row_number,
            'data_row_index': article.row_number - 1,
            'title': article.title,
            'status': article.status,
            'status_display': article.get_status_display(),
            'error_message': article.error_message,
        }
        for article in job.articles.all().order_by('row_number')
    ]
    completed_rows = sum(1 for a in job.articles.all() if a.status == ArticleResult.Status.COMPLETED)
    failed_rows = sum(1 for a in job.articles.all() if a.status == ArticleResult.Status.FAILED)
    progress_value = 0 if not job.total_rows else round((completed_rows + failed_rows) / job.total_rows * 100)
    return JsonResponse({
        'status': job.status,
        'status_display': job.get_status_display(),
        'completed_rows': completed_rows,
        'failed_rows': failed_rows,
        'total_rows': job.total_rows,
        'progress': progress_value,
        'progress_text': f'{completed_rows + failed_rows}/{job.total_rows} rows processed',
        'output_sheet_url': '',
        'spreadsheet_id': job.spreadsheet_id or '',
        'is_complete': job.status in {
            GenerationJob.Status.COMPLETED,
            GenerationJob.Status.PARTIAL,
            GenerationJob.Status.FAILED,
            GenerationJob.Status.CANCELLED,
        },
        'articles': articles_data,
    })


@login_required
def job_status(request, job_id):
    job = get_object_or_404(
        GenerationJob.objects.prefetch_related('articles'),
        pk=job_id,
    )
    articles = job.articles.all()
    for article in articles:
        article.data_row_index = article.row_number - 1
    return render(
        request,
        'generator/status.html',
        {
            'job': job,
            'articles': articles,
        },
    )


@login_required
def stop_job(request, job_id):
    if request.method == 'POST':
        job = get_object_or_404(GenerationJob, pk=job_id)
        if job.status in (GenerationJob.Status.PENDING, GenerationJob.Status.PROCESSING):
            job.status = GenerationJob.Status.CANCELLED
            job.save(update_fields=['status'])
        return redirect('job_status', job_id=job.pk)
    return redirect('job_status', job_id=job_id)


@login_required
def resume_job(request, job_id):
    if request.method == 'POST':
        job = get_object_or_404(GenerationJob, pk=job_id)
        if job.status in (GenerationJob.Status.CANCELLED, GenerationJob.Status.FAILED):
            job.status = GenerationJob.Status.PENDING
            job.save(update_fields=['status'])
            threading.Thread(target=_run_async_job, args=(job.pk,), daemon=True).start()
        return redirect('job_status', job_id=job.pk)
    return redirect('job_status', job_id=job_id)
