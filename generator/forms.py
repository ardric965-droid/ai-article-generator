from django import forms


class CsvUploadForm(forms.Form):
    csv_file = forms.FileField(
        label='CSV file',
        help_text='Upload a UTF-8 CSV file with title and description columns.',
    )

    def clean_csv_file(self):
        uploaded_file = self.cleaned_data['csv_file']
        filename = uploaded_file.name.lower()

        if not filename.endswith('.csv'):
            raise forms.ValidationError('Only CSV files are allowed.')

        content_type = getattr(uploaded_file, 'content_type', '')
        allowed_types = {
            'text/csv',
            'application/csv',
            'text/plain',
            'application/vnd.ms-excel',
            '',
        }
        if content_type and content_type not in allowed_types:
            raise forms.ValidationError('Only CSV files are allowed.')

        return uploaded_file
