import io

from django.test import SimpleTestCase

from generator.services.csv_service import parse_csv_file


def _csv_bytes(content: str) -> io.BytesIO:
    return io.BytesIO(content.encode('utf-8'))


def _csv_bytes_with_bom(content: str) -> io.BytesIO:
    return io.BytesIO(content.encode('utf-8-sig'))


class ParseCsvFileValidTests(SimpleTestCase):
    def test_parses_valid_csv_with_few_rows(self):
        uploaded = _csv_bytes(
            'title,description\n'
            'First title,First description\n'
            'Second title,Second description\n'
        )

        rows = parse_csv_file(uploaded)

        self.assertEqual(
            rows,
            [
                {'title': 'First title', 'description': 'First description'},
                {'title': 'Second title', 'description': 'Second description'},
            ],
        )

    def test_parses_valid_csv_with_more_than_twenty_rows(self):
        lines = ['title,description']
        for index in range(25):
            lines.append(f'Title {index},Description {index}')
        uploaded = _csv_bytes('\n'.join(lines))

        rows = parse_csv_file(uploaded)

        self.assertEqual(len(rows), 25)
        self.assertEqual(rows[0]['title'], 'Title 0')
        self.assertEqual(rows[-1]['description'], 'Description 24')

    def test_parses_utf8_with_bom(self):
        uploaded = _csv_bytes_with_bom(
            'title,description\n'
            'BOM title,BOM description\n'
        )

        rows = parse_csv_file(uploaded)

        self.assertEqual(
            rows,
            [{'title': 'BOM title', 'description': 'BOM description'}],
        )

    def test_accepts_case_insensitive_headers_and_strips_values(self):
        uploaded = _csv_bytes(
            ' Title , Description \n'
            '  Trimmed title  ,  Trimmed description  \n'
        )

        rows = parse_csv_file(uploaded)

        self.assertEqual(
            rows,
            [{'title': 'Trimmed title', 'description': 'Trimmed description'}],
        )


class ParseCsvFileInvalidTests(SimpleTestCase):
    def test_rejects_missing_title_column(self):
        uploaded = _csv_bytes('description\nOnly description\n')

        with self.assertRaisesMessage(
            ValueError,
            'CSV file must include a "title" column.',
        ):
            parse_csv_file(uploaded)

    def test_rejects_missing_description_column(self):
        uploaded = _csv_bytes('title\nOnly title\n')

        with self.assertRaisesMessage(
            ValueError,
            'CSV file must include a "description" column.',
        ):
            parse_csv_file(uploaded)

    def test_rejects_empty_title(self):
        uploaded = _csv_bytes(
            'title,description\n'
            ',Has description\n'
        )

        with self.assertRaisesMessage(
            ValueError,
            'Row 2: title must not be empty.',
        ):
            parse_csv_file(uploaded)

    def test_rejects_empty_description(self):
        uploaded = _csv_bytes(
            'title,description\n'
            'Has title,\n'
        )

        with self.assertRaisesMessage(
            ValueError,
            'Row 2: description must not be empty.',
        ):
            parse_csv_file(uploaded)

    def test_rejects_header_only_csv(self):
        uploaded = _csv_bytes('title,description\n')

        with self.assertRaisesMessage(
            ValueError,
            'CSV file must contain at least one data row.',
        ):
            parse_csv_file(uploaded)

    def test_rejects_empty_file(self):
        uploaded = _csv_bytes('')

        with self.assertRaisesMessage(ValueError, 'CSV file is empty.'):
            parse_csv_file(uploaded)

    def test_rejects_non_utf8_encoding(self):
        uploaded = io.BytesIO('title,description\n'.encode('latin-1') + b'\xff\xfe')

        with self.assertRaisesMessage(
            ValueError,
            'CSV file must be UTF-8 encoded.',
        ):
            parse_csv_file(uploaded)

    def test_rejects_duplicate_required_columns(self):
        uploaded = _csv_bytes(
            'title,Title,description\n'
            'A title,A description\n'
        )

        with self.assertRaisesMessage(
            ValueError,
            'CSV file contains duplicate "title" column.',
        ):
            parse_csv_file(uploaded)
