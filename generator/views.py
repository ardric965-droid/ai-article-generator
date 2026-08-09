from pathlib import Path
import threading

from django.conf import settings
from django.db import close_old_connections
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from generator.forms import CsvUploadForm
from generator.models import ArticleResult, GenerationJob
from generator.services.csv_service import parse_csv_file
from generator.services.processing_service import process_job


def _run_async_job(job_id: int):
    try:
        process_job(job_id) 
    finally:
        close_old_connections()


def upload_csv(request):
    if request.method == 'POST':
        form = CsvUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = form.cleaned_data['csv_file']
            try:
                rows = parse_csv_file(csv_file)
            except ValueError as exc:
                form.add_error('csv_file', str(exc))
            else:
                job = GenerationJob.objects.create(
                    uploaded_file=csv_file,
                    total_rows=len(rows),
                    status=GenerationJob.Status.PENDING,
                )
                ArticleResult.objects.bulk_create([
                    ArticleResult(
                        job=job,
                        row_number=index,
                        title=row['title'],
                        description=row['description'],
                    )
                    for index, row in enumerate(rows, start=1)
                ])
                
                # Launch thread to process the job asynchronously
                threading.Thread(target=_run_async_job, args=(job.pk,), daemon=True).start()
                
                return redirect('job_status', job_id=job.pk)
    else:
        form = CsvUploadForm()

    return render(request, 'generator/upload.html', {'form': form})


def job_status_api(request, job_id):
    job = get_object_or_404(
        GenerationJob.objects.prefetch_related('articles'),
        pk=job_id,
    )
    articles_data = [
        {
            'row_number': article.row_number,
            'title': article.title,
            'status': article.status,
            'status_display': article.get_status_display(),
            'error_message': article.error_message,
        }
        for article in job.articles.all().order_by('row_number')
    ]
    output_available = bool(
        job.output_file
        and (Path(settings.OUTPUTS_DIR) / job.output_file).exists()
    )
    completed_rows = sum(1 for a in job.articles.all() if a.status == ArticleResult.Status.COMPLETED)
    failed_rows = sum(1 for a in job.articles.all() if a.status == ArticleResult.Status.FAILED)
    return JsonResponse({
        'status': job.status,
        'status_display': job.get_status_display(),
        'completed_rows': completed_rows,
        'failed_rows': failed_rows,
        'total_rows': job.total_rows,
        'output_available': output_available,
        'articles': articles_data,
    })


def job_status(request, job_id):
    job = get_object_or_404(
        GenerationJob.objects.prefetch_related('articles'),
        pk=job_id,
    )
    output_available = bool(
        job.output_file
        and (Path(settings.OUTPUTS_DIR) / job.output_file).exists()
    )

    return render(
        request,
        'generator/status.html',
        {
            'job': job,
            'articles': job.articles.all(),
            'output_available': output_available,
        },
    )


def download_result(request, job_id):
    job = get_object_or_404(GenerationJob, pk=job_id)

    if not job.output_file:
        raise Http404('No result file is available for this job.')

    output_path = Path(settings.OUTPUTS_DIR) / job.output_file
    if not output_path.is_file():
        raise Http404('Result file was not found.')

    return FileResponse(
        output_path.open('rb'),
        as_attachment=True,
        filename=job.output_file,
        content_type='text/plain; charset=utf-8',
    )


def stop_job(request, job_id):
    if request.method == 'POST':
        job = get_object_or_404(GenerationJob, pk=job_id)
        if job.status in (GenerationJob.Status.PENDING, GenerationJob.Status.PROCESSING):
            job.status = GenerationJob.Status.CANCELLED
            job.save(update_fields=['status'])
        return redirect('job_status', job_id=job.pk)
    return redirect('job_status', job_id=job_id)
