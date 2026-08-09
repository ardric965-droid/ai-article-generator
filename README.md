# AI Article Generator

A beginner-friendly, production-ready Django application that parses bulk article prompts from an uploaded CSV, generates content asynchronously using the Groq LLM API, and outputs a combined `.txt` document of all generated articles.

---

## 🚀 Key Features

*   **Asynchronous Bulk Processing:** Processes uploaded CSV files containing any number of rows in a background thread to prevent browser request timeouts.
*   **Gemini/Groq API Integration:** Generates unique, highly engaging articles based on titles and descriptions using Groq completions with built-in retry-backoff logic for transient API issues.
*   **Dynamic Progress Dashboard:** Real-time JavaScript progress tracker displaying progress percentage, status updates (Pending, Generating, Completed, Failed), and dynamic output links.
*   **Job Cancellation:** Enables users to stop active generation jobs mid-process, saving work compiled up to that point.
*   **Robust CSV Parser:** Custom validation engine ensuring required columns (`title` and `description`) exist, mapping case-insensitive headers, and isolating row-level empty field errors.
*   **Unified Formatting:** Compiles all successful generations into a single downloadable UTF-8 `.txt` file, listing failures and associated API error logs at the bottom.

---

## 🛠️ Technology Stack

*   **Web Framework:** Django 5.2 (Python)
*   **Database:** SQLite 3 (ORM persistence layer)
*   **Services Layer:** Decoupled modules for parsing, API integration, compiler formatting, and queue loop orchestration
*   **Task Management:** Lightweight Python `threading.Thread` background daemon execution
*   **Frontend UI:** Vanilla HTML5, CSS3 (using Google Fonts and modern typography variables), and client-side Vanilla JS polling

---

## 📐 System Architecture

The project leverages a decoupled, service-oriented structure around the standard Model-View-Template (MVT) pattern:

```
[ Browser / Client ]              [ Django Views / Services ]           [ DB / Disk / LLM ]
         │                                     │                                 │
         │─── 1. POST CSV Upload ─────────────>│                                 │
         │                                     │─── 2. Parse & Validate CSV ────>│
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
         │                                     │                                 │  3. Compile final combined output
         │                                     │                                 │  4. Write atomic TXT file to disk
         │                                     │                                 │  5. Update Job status in DB
         │                                     │                                 │  ▲
         │─── 7. GET API Progress (2s) ───────>│                                 │  │
         │                                     │─── 8. Query job progress ──────>│  │
         │<── 9. Update UI DOM Elements ───────│                                 │──┘
         │                                     │
         │─── 10. Click Download Button ──────>│
         │<── 11. FileResponse (TXT file) ─────│
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
Install Django and its configurations:
```bash
pip install Django python-dotenv
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
```

### 4. Run Migrations & Launch Server
Execute database setups and start the local development web server:
```bash
# Apply SQLite database schemas
python manage.py migrate

# Run the local server
python manage.py runserver
```
Navigate to `http://127.0.0.1:8000/` in your browser.

---

## 🧪 Running Unit Tests

The project includes unit and integration tests covering views, services, cancellation workflows, and error handling configurations.

To run the full suite:
```bash
python manage.py test
```

---

## 📦 Project Codebase Structure

*   `config/`: Main Django settings and root routing patterns.
*   `generator/`: Core application module.
    *   `models.py`: Defines `GenerationJob` and `ArticleResult` schemas.
    *   `views.py`: Coordinates HTTP request endpoints, redirects, and background threading.
    *   `forms.py`: Handles CSV file upload validation.
    *   `services/`:
        *   `csv_service.py`: Parses, decodes, and validates input CSV schemas.
        *   `llm_service.py`: Manages Groq API calls, prompts, timeouts, and exponential backoff retry cycles.
        *   `output_service.py`: Compiles completed article documents and error reports into unified `.txt` files.
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
3.  **Authentication and Rate Limiting:**
    *   *Production Goal:* Implement user authentication and apply rate-limiting constraints to the API and uploads views to control LLM costs and protect against API abuse.
