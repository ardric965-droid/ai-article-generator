from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from generator.forms import CsvUploadForm
from generator.models import ArticleResult, GenerationJob
from generator.services.csv_service import parse_csv_file
from generator.services.processing_service import process_job


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
                process_job(job.pk)
                return redirect('job_status', job_id=job.pk)
    else:
        form = CsvUploadForm()

    return render(request, 'generator/upload.html', {'form': form})


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
