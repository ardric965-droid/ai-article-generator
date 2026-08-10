# AI Article Generator

A beginner-friendly Django application that generates articles from Google Sheet rows using the Groq LLM API, writes the results back to the same Google Sheet under `content`, `status`, and `error` columns, and exposes a simple job dashboard for monitoring, cancellation, and resume.

---

## 🚀 Key Features

*   **Spreadsheet-Driven Workflow:** Reads article ideas from a Google Sheet, validates the sheet structure, and writes the generated articles back to the **same** Google Sheet under `content`, `status`, and `error` columns.
*   **Asynchronous Bulk Processing:** Processes rows in a background thread so the web request can return quickly.
*   **LLM JSON Validation:** Validates the Groq response shape, rejects malformed payloads, and uses the returned content field safely.
*   **Dynamic Progress Dashboard:** Polls the status endpoint every two seconds to update progress, row statuses, and job completion state.
*   **Job Cancellation and Resume:** Allows users to stop a running job and resume it later without reprocessing completed rows.
*   **Write-Back Results:** Writes results back to the original Google Sheet under `content`, `status`, and `error` columns.

---

## 🛠️ Technology Stack

*   **Web Framework:** Django 5.2 (Python)
*   **Database:** SQLite 3 (ORM persistence layer)
*   **Services Layer:** Decoupled modules for Google Sheets access (read input, write and share output), API integration, and queue loop orchestration
*   **Task Management:** Lightweight Python `threading.Thread` background daemon execution
*   **Frontend UI:** Vanilla HTML5, CSS3 (using Google Fonts and modern typography variables), and client-side Vanilla JS polling

---

## 📐 System Architecture

The project leverages a decoupled, service-oriented structure around the standard Model-View-Template (MVT) pattern:

```
[ Browser / Client ]              [ Django Views / Services ]           [ DB / Sheets / LLM ]
         │                                     │                                 │
         │─── 1. Paste Google Sheet URL ───────>│                                 │
         │                                     │─── 2. Validate & read rows ──────>│
         │                                     │<── 3. Return valid rows ────────│
         │                                     │                                 │
         │                                     │─── 4. Save Job & Rows (DB) ────>│
         │                                     │                                 │
         │                                     │─── 5. Launch Background Thread ─│──┐
         │                                     │                                 │  │ (Async Execution)
         │<── 6. Redirect to Status URL ───────│                                 │  │
         │                                     │                                 │  ▼
         │                                     │                                 │  [ Thread Loop ]
         │                                     │                                 │  1. Job status -> 'processing'
         │                                     │                                 │  2. Loop each article:
         │                                     │                                 │     - Call Groq completions API
         │                                     │                                 │     - Update row status in DB
         │                                     │                                 │  3. Write results back to the input sheet
         │                                     │                                 │  4. Ensure output columns exist in sheet
         │                                     │                                 │  5. Update Job status in DB
         │                                     │                                 │  ▲
         │─── 7. GET API Progress (2s) ───────>│                                 │  │
         │                                     │─── 8. Query job progress ──────>│  │
         │<── 9. Update UI DOM Elements ───────│                                 │──┘
         │                                     │
         │─── 10. Open original Google Sheet ──│
         │<── 11. Open original Google Sheet ─────│
```

---

## ⚙️ Setup & Installation

### 1. Clone the Repository & Initialize Environment
Clone the project directory locally, then open your terminal inside the root directory.

```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows (Command Prompt):
venv\Scripts\activate.bat
# On Windows (PowerShell):
venv\Scripts\Activate.ps1
# On macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependencies
Install the project dependencies inside the existing virtual environment:
```bash
pip install Django python-dotenv google-auth google-api-python-client
```

### 3. Setup Environment Variables
Copy the example environment template file and add your credentials:
```bash
cp .env.example .env
```
Open the newly created `.env` file and populate it:
```env
SECRET_KEY=your-django-secret-key
LLM_API_KEY=gsk_your_groq_api_key_here
GOOGLE_CREDENTIALS_FILE=google_credentials.json
```

### 4. Create a User Account
The app uses Django's built-in authentication and has no self-service sign-up page, so create an account before logging in:
```bash
python manage.py createsuperuser
```

### 5. Run Migrations & Launch Server
Execute database setups and start the local development web server:
```bash
# Apply SQLite database schemas
python manage.py migrate

# Run the local server
python manage.py runserver
```
Navigate to `http://127.0.0.1:8000/`, log in with the account from step 4, and paste a Google Sheet URL to create a job.

---

## 🧪 Running Unit Tests

The project includes unit and integration tests covering views, services, cancellation workflows, progress polling, and LLM response validation.

To run the full test suite:
```bash
python manage.py test
```

---

## 📦 Project Codebase Structure

*   `config/`: Main Django settings and root routing patterns.
*   `generator/`: Core application module.
    *   `models.py`: Defines `GenerationJob` and `ArticleResult` schemas.
    *   `views.py`: Coordinates HTTP request endpoints, redirects, and background threading.
    *   `forms.py`: Handles Google Sheet URL validation.
    *   `services/`:
        *   `google_sheets_service.py`: Reads rows from and writes results (`content`/`status`/`error`) back to the user's input Google Sheet.
        *   `llm_service.py`: Manages Groq API calls, prompts, timeouts, and exponential backoff retry cycles.
        *   `processing_service.py`: Orchestrates job queues, loops rows, and handles cancellation markers.
    *   `templates/`: HTML rendering templates with built-in responsive styling and progress script hooks.

---

## 🚧 Production Roadmap & Tradeoffs

To facilitate quick deployment and assessment, this app makes specific design choices that should be optimized for a large-scale production setup:

1.  **Task Management (Local Threads vs. Celery):**
    *   *Current Choice:* `threading.Thread`. Minimizes setup complexity.
    *   *Production Goal:* Replace with **Celery** + **Redis**. If the web server crashes or restarts, active local threads die and jobs become permanently locked in "processing". Celery tasks persist independently, support queue limits, and handle server crashes gracefully.
2.  **Database Engine (SQLite vs. PostgreSQL):**
    *   *Current Choice:* SQLite 3. Self-contained on disk.
    *   *Production Goal:* **PostgreSQL**. Background writing tasks in multi-threaded SQLite setups can cause file locking errors (`database is locked`) when traffic spikes. PostgreSQL handles heavy concurrent read/write transactions seamlessly.
3.  **Account Management and Rate Limiting:**
    *   *Current Choice:* Django's built-in authentication (login/logout) with admin-created accounts.
    *   *Production Goal:* Add self-service registration, email verification, and rate-limiting constraints on the API and upload views to control LLM costs and protect against abuse.
