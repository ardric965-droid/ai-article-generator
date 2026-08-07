import csv
import io

REQUIRED_COLUMNS = ('title', 'description')


def _normalize_header(name: str) -> str:
    return name.strip().lower()


def _decode_csv_content(uploaded_file) -> str:
    if hasattr(uploaded_file, 'read'):
        raw = uploaded_file.read()
        if hasattr(uploaded_file, 'seek'):
            uploaded_file.seek(0)
    else:
        raw = uploaded_file

    if isinstance(raw, str):
        if raw.startswith('\ufeff'):
            return raw[1:]
        return raw

    if isinstance(raw, bytes):
        try:
            return raw.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('CSV file must be UTF-8 encoded.') from exc

    raise ValueError('CSV file must be a readable file or byte string.')


def _build_column_map(fieldnames: list[str]) -> dict[str, str]:
    column_map: dict[str, str] = {}
    for header in fieldnames:
        if header is None:
            continue
        normalized = _normalize_header(header)
        if normalized in column_map:
            raise ValueError(f'CSV file contains duplicate "{normalized}" column.')
        column_map[normalized] = header
    return column_map


def parse_csv_file(uploaded_file) -> list[dict[str, str]]:
    """Validate an uploaded CSV and return cleaned row dictionaries.

    Each dictionary contains ``title`` and ``description`` keys with stripped
    non-empty string values. Raises ``ValueError`` when validation fails.
    """
    text = _decode_csv_content(uploaded_file)

    if not text.strip():
        raise ValueError('CSV file is empty.')

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise ValueError('CSV file must include a header row.')

    column_map = _build_column_map(list(reader.fieldnames))

    for column in REQUIRED_COLUMNS:
        if column not in column_map:
            raise ValueError(f'CSV file must include a "{column}" column.')

    rows: list[dict[str, str]] = []

    for line_number, row in enumerate(reader, start=2):
        title = (row.get(column_map['title']) or '').strip()
        description = (row.get(column_map['description']) or '').strip()

        if not title:
            raise ValueError(f'Row {line_number}: title must not be empty.')
        if not description:
            raise ValueError(f'Row {line_number}: description must not be empty.')

        rows.append({'title': title, 'description': description})

    if not rows:
        raise ValueError('CSV file must contain at least one data row.')

    return rows
