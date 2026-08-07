import tempfile
from pathlib import Path

from django.conf import settings

from generator.models import ArticleResult

SECTION_SEPARATOR = '=' * 60


def _safe_filename(filename: str) -> str:
    safe_name = Path(filename).name
    if not safe_name or safe_name in {'.', '..'}:
        raise ValueError('Invalid output filename.')
    return safe_name


def _format_article_section(article: ArticleResult) -> str:
    return (
        f'{SECTION_SEPARATOR}\n'
        f'ARTICLE {article.row_number}\n'
        f'TITLE: {article.title}\n'
        f'{SECTION_SEPARATOR}\n\n'
        f'{article.article.strip()}\n'
    )


def _format_error_section(failed_articles: list[ArticleResult]) -> str:
    if not failed_articles:
        return ''

    lines = [
        SECTION_SEPARATOR,
        'ERRORS',
        SECTION_SEPARATOR,
        '',
    ]

    for article in failed_articles:
        error_message = article.error_message.strip() or 'Unknown error.'
        lines.extend([
            f'ROW {article.row_number}',
            f'TITLE: {article.title}',
            f'ERROR: {error_message}',
            '',
        ])

    return '\n'.join(lines)


def build_output_content(articles: list[ArticleResult]) -> str:
    """Build the combined TXT content from ArticleResult records."""
    sorted_articles = sorted(articles, key=lambda article: article.row_number)
    successful = [
        article
        for article in sorted_articles
        if article.status == ArticleResult.Status.COMPLETED
    ]
    failed = [
        article
        for article in sorted_articles
        if article.status == ArticleResult.Status.FAILED
    ]

    sections = [_format_article_section(article) for article in successful]

    error_section = _format_error_section(failed)
    if error_section:
        sections.append(error_section)

    if not sections:
        return ''

    return '\n'.join(sections).rstrip() + '\n'


def write_combined_output(
    articles: list[ArticleResult],
    filename: str | None = None,
) -> Path:
    """Write a combined UTF-8 TXT file to the outputs directory.

    Returns the full path to the written file.
    """
    if not articles:
        raise ValueError('At least one ArticleResult is required.')

    outputs_dir = Path(settings.OUTPUTS_DIR)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        filename = f'job_{articles[0].job_id}_articles.txt'

    output_path = outputs_dir / _safe_filename(filename)
    temp_path = output_path.with_name(f'.{output_path.name}.tmp')

    content = build_output_content(articles)

    try:
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(output_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise
    finally:
        if temp_path.exists() and temp_path != output_path:
            temp_path.unlink(missing_ok=True)

    return output_path
