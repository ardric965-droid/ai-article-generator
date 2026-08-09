# Project Instructions

Build a beginner-friendly Django application.

## Requirements
- Use Python and Django.
- Use Django templates, HTML, and CSS.
- Use SQLite.
- - Accept a CSV file with any number of data rows, including fewer or more than 20.
- Require title and description columns.
- Generate one article per row through an LLM API.
- Store job and article status using Django models.
- Save one combined UTF-8 TXT file locally.
- Allow the user to download the TXT file.
- Store API keys in .env.
- Never expose API keys in frontend code.
- Use separate services for CSV validation, LLM calls, and TXT output.
- Write tests for validation and output generation.

## Restrictions
- Do not use Streamlit.
- Do not use React.
- Do not use LangChain.
- Do not use Docker initially.
- Do not add unnecessary packages.
- Do not modify unrelated files.
- Explain changes before making them.