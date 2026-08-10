import re

from django import forms


class SpreadsheetUploadForm(forms.Form):
    spreadsheet_url = forms.CharField(
        label='Google Sheet URL',
        help_text='Paste a Google Sheets URL or spreadsheet ID with title and description columns.',
        widget=forms.TextInput(attrs={'placeholder': 'https://docs.google.com/spreadsheets/d/...'}),
    )

    def clean_spreadsheet_url(self):
        spreadsheet_url = self.cleaned_data['spreadsheet_url'].strip()
        if not spreadsheet_url:
            raise forms.ValidationError('Please enter a Google Sheets URL or spreadsheet ID.')
        # Raw spreadsheet IDs only: require a minimum length (real Google Sheet
        # IDs are ~44 characters) so obviously invalid strings like
        # "not-a-sheet-link" fail here instead of hitting the API.
        if not re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', spreadsheet_url) \
                and not re.match(r'^[a-zA-Z0-9-_]{25,}$', spreadsheet_url):
            raise forms.ValidationError('Enter a valid Google Sheets URL or spreadsheet ID.')
        return spreadsheet_url
