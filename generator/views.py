import threading

from django.contrib.auth.decorators import login_required
from django.db import close_old_connections, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from generator.forms import SignUpForm, SpreadsheetUploadForm
from generator.models import ArticleResult, GenerationJob

try:
    from generator.services.google_sheets_service import (
        classify_rows_for_job,
        extract_spreadsheet_id,
        read_sheet_rows,
        validate_sheet_connection,
    )
except ModuleNotFoundError:
    def read_sheet_rows(*args, **kwargs):
        raise RuntimeError('Google Sheets dependencies are not installed.')

    def validate_sheet_connection(*args, **kwargs):
        raise RuntimeError('Google Sheets dependencies are not installed.')

    def extract_spreadsheet_id(*args, **kwargs):
        raise RuntimeError('Google Sheets dependencies are not installed.')

    def classify_rows_for_job(*args, **kwargs):
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
def upload_spreadsheet(request):
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
                    )
                    for row in rows
                ])

                threading.Thread(target=_run_async_job, args=(job.pk,), daemon=True).start()

                return redirect('job_status', job_id=job.pk)
    else:
        form = SpreadsheetUploadForm()

    return render(request, 'generator/upload.html', {'form': form})


def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})


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


def _resolve_sheet(request):
    """Extract the spreadsheet id, validate the connection and read rows.

    Returns a ``(spreadsheet_id, rows)`` tuple. Any failure raises an
    exception which the caller converts into a 400 JSON response.
    """
    sheet_url = (request.POST.get('spreadsheet_url') or '').strip()
    if not sheet_url:
        raise ValueError('Please enter a Google Sheets URL or spreadsheet ID.')
    spreadsheet_id = extract_spreadsheet_id(sheet_url)
    validate_sheet_connection(sheet_url)
    rows = read_sheet_rows(spreadsheet_id)
    return spreadsheet_id, rows


@login_required
def preview_generation(request):
    """Preview a sheet submission, reporting already-completed rows.

    Used by the enhanced upload flow before the user confirms generation. The
    plain ``upload_spreadsheet`` form POST remains as a non-JS fallback.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)

    try:
        spreadsheet_id, rows = _resolve_sheet(request)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    classification = classify_rows_for_job(rows)
    existing_job = GenerationJob.objects.filter(
        spreadsheet_id=spreadsheet_id,
    ).first()

    all_completed = classification['all_completed']
    completed_count = classification['completed_count']
    pending_count = classification['pending_count']

    if all_completed:
        message = (
            "Article generation for this sheet is already completed. "
            "No rows need to be regenerated."
        )
    else:
        message = (
            f"{completed_count} articles are already completed. "
            f"Only the remaining {pending_count} rows will be processed."
        )

    sheet_url = f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit'

    return JsonResponse({
        'sheet_id': spreadsheet_id,
        'sheet_url': sheet_url,
        'job_exists': existing_job is not None,
        'existing_job_id': existing_job.pk if existing_job else None,
        'existing_job_status': existing_job.status if existing_job else None,
        'total_rows': completed_count + pending_count,
        'completed_count': completed_count,
        'pending_count': pending_count,
        'all_completed': all_completed,
        'message': message,
    })


@login_required
def create_generation_job(request):
    """Create (or reset) a generation job for a sheet and start processing.

    Already-completed rows (detected from the sheet's ``status``/``content``
    columns) are pre-marked ``completed`` so the background thread only
    processes the pending/failed rows. Re-submitting a sheet whose job is
    already ``pending``/``processing`` reuses that job and starts no thread.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)

    try:
        spreadsheet_id, rows = _resolve_sheet(request)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    classification = classify_rows_for_job(rows)
    all_completed = classification['all_completed']
    completed_count = classification['completed_count']
    pending_count = classification['pending_count']

    if all_completed:
        return JsonResponse(
            {
                'error': (
                    "Article generation for this sheet is already completed. "
                    "No rows need to be regenerated."
                )
            },
            status=400,
        )

    sheet_url = f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit'
    reuse_existing = False

    with transaction.atomic():
        job, created = GenerationJob.objects.get_or_create(
            spreadsheet_id=spreadsheet_id,
            defaults={
                'status': GenerationJob.Status.PENDING,
                'total_rows': len(rows),
                'user': request.user,
            },
        )

        if not created and job.status in (
            GenerationJob.Status.PENDING,
            GenerationJob.Status.PROCESSING,
        ):
            # An active job already exists for this sheet; reuse it rather than
            # spawning a duplicate thread or overwriting its results.
            reuse_existing = True
        else:
            if not created:
                job.status = GenerationJob.Status.PENDING
                job.total_rows = len(rows)
                job.user = job.user or request.user
                job.save(update_fields=['status', 'total_rows', 'user'])

            # Drop any ArticleResult rows that no longer exist in the sheet
            # (e.g. rows were removed between submissions).
            current_row_numbers = {row['row_number'] for row in rows}
            job.articles.exclude(row_number__in=current_row_numbers).delete()

            for row in rows:
                status = (row.get('status') or '').strip().lower()
                content = (row.get('content') or '').strip()
                is_completed = status == 'completed' and content
                ArticleResult.objects.update_or_create(
                    job=job,
                    row_number=row['row_number'],
                    defaults={
                        'title': row['title'],
                        'description': row['description'],
                        'status': (
                            ArticleResult.Status.COMPLETED
                            if is_completed
                            else ArticleResult.Status.PENDING
                        ),
                        'article': content if is_completed else '',
                        'error_message': row.get('error', '') if is_completed else '',
                    },
                )

    if reuse_existing:
        return JsonResponse({
            'job_id': job.pk,
            'message': 'A generation job for this sheet is already running.',
            'pending_count': pending_count,
            'completed_count': completed_count,
        })

    threading.Thread(target=_run_async_job, args=(job.pk,), daemon=True).start()

    return JsonResponse({
        'job_id': job.pk,
        'message': 'Generation job created. Only incomplete rows will be processed.',
        'pending_count': pending_count,
        'completed_count': completed_count,
        'sheet_url': sheet_url,
    })
