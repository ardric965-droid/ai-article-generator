---
description: 
---

I want to understand this existing project completely before making any changes.

Do not modify, delete, rename, or create any files.
Do not run migrations or install packages.
Only inspect the project and explain it.


Explain the project in the following order.

1. PROJECT STRUCTURE
Show the complete directory tree, excluding:
- venv
- __pycache__
- .git
- node_modules
- generated or temporary files

For every folder and file, explain:
- What it is
- Why it exists
- What part of the application uses it
- What would happen if it were removed

2. DJANGO ARCHITECTURE
Explain how these Django parts work in this project:
- config/settings.py
- config/urls.py
- generator/models.py
- generator/views.py
- generator/urls.py
- templates
- static files
- migrations
- manage.py
- SQLite database

Explain the relationship between URLs, views, models, templates, and services.

3. MODEL EXPLANATION
Explain every model in models.py:
- Every field
- Field type
- Why that field is needed
- Relationships between models
- Possible values for each status field
- How GenerationJob relates to ArticleResult

Show an example of what one real job and its article records look like in the database.

4. COMPLETE REQUEST FLOW
Trace one complete example from beginning to end:

Input:
A user uploads a CSV containing three rows.

Explain exactly:
- Which URL receives the request
- Which view handles it
- How the uploaded file is accessed
- How the CSV is validated
- How database records are created
- When the background thread starts
- What argument is passed to the thread
- Which function runs inside the thread
- How each ArticleResult is processed
- How the LLM service is called
- How the database is updated
- How the TXT file is created
- How the user sees progress
- How the final download works

Show this as both:
A. A numbered explanation
B. An ASCII flow diagram

5. THREADING EXPLANATION
Explain:
- What threading.Thread does here
- Why threading is used
- What the main Django request does
- What the background thread does
- Why the request can return before generation finishes
- How the thread updates the database
- Why only one thread should be created per job
- What happens if Django stops
- Why Celery and Redis might be preferred in production

Explain this using the actual functions and files in this project, not generic examples.

6. CSV PROCESSING
Explain:
- Which file reads the CSV
- Whether csv.DictReader or another method is used
- How column names are validated
- How empty rows are handled
- How any number of rows is supported
- How invalid files are reported

7. LLM API FLOW
Explain:
- Where the API key is loaded
- Where the prompt is constructed
- Which function sends the API request
- What data is sent to the LLM
- How the response is extracted
- How timeout and API errors are handled
- Why the API key must not be placed in HTML or JavaScript

Do not display or expose the real API key.

8. JAVASCRIPT PROGRESS FLOW
Explain:
- Which JavaScript file is used
- Which JSON endpoint it calls
- What data the endpoint returns
- How fetch() works here
- How often polling occurs
- How the progress percentage is calculated
- When polling stops
- When the download link becomes visible

9. TXT OUTPUT FLOW
Explain:
- Which service creates the TXT file
- Where the file is saved
- How article titles and row numbers are formatted
- How failed rows are represented
- How the file is returned to the user for download

10. ERROR SCENARIOS
Explain what happens when:
- The CSV is not provided
- The CSV has the wrong columns
- The CSV has zero rows
- A title is empty
- A description is empty
- The LLM API fails
- One row fails but other rows succeed
- The background thread stops
- The TXT file cannot be created

11. FILE-BY-FILE LEARNING GUIDE
Create a table with these columns:
- File
- Main responsibility
- Important functions/classes
- Files it depends on
- Files that depend on it
- What I should understand before editing it

12. INTERVIEW EXPLANATION
Give me a simple two-minute explanation that I can use in a technical interview to describe:
- The project
- The architecture
- The CSV-to-article workflow
- The use of threading
- The use of models.py
- The use of JavaScript polling
- The main production limitation

13. PROJECT GAPS
At the end, list:
- What is already implemented
- What is incomplete
- Any bugs or risks you find
- Any missing tests
- Any improvements appropriate for a junior-level assessment

Do not change the code.
Do not assume a file exists.
If the actual code differs from the project description, explain the difference clearly.
Use beginner-friendly language and refer to actual file names and function names.