# Development and operations

## Local Python setup

From the repository root, using Python 3.12:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-ml.txt -r backend\requirements-tensorflow.txt -r backend\requirements-ocr.txt
Copy-Item .env.example backend\.env
# Replace JWT_SECRET_KEY in backend/.env with a unique random signing key.
docker compose up -d postgres redis
```

Compose requires a root `.env` signing key even when only starting infrastructure. Use `scripts/start.ps1` to initialize one, or generate it yourself. Local Python reads `backend/.env` when commands run from `backend`; Docker uses root `.env`. Keep both out of Git.

Run these in separate terminals from `backend`:

```powershell
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

```powershell
..\.venv\Scripts\python.exe -m celery -A app.tasks worker --loglevel=info --pool=solo
```

```powershell
..\.venv\Scripts\python.exe -m celery -A app.tasks beat --loglevel=info
```

Beat is required to dispatch committed outbox jobs. The default dispatcher interval is five seconds. Use one Beat scheduler. CPU inference can take longer than this interval; first use downloads assets.

From `frontend`, run `npm ci` and `npm run dev`. Vite proxies API calls to `localhost:8000`. The public `/demo` works even when these backend processes are stopped.

## Existing databases

Back up application databases before applying the upgrade. Migration `e62f9140b3a1` adds complete stage evidence, selfie frame paths, an outbox and a unique index limiting each user to one editable application.

If legacy data contains multiple pending, processing, review-ready or error applications for one user, the migration fails rather than silently deleting records. Review and resolve those duplicates explicitly. The migration also normalizes the previous `kyc_standard` document-rule type to `idv_standard`.

Completed pipeline results are preserved. Retries return the original automated decision even when a reviewer has subsequently changed the application's status. Legacy results can be displayed without complete stage arrays.

The downgrade removes new evidence columns and the outbox; restore a backup when those records must be retained. It leaves audit performers nullable to preserve automated audit events.

## Troubleshooting

- **Processing never starts:** confirm both `celery-worker` and `celery-beat` are running; inspect their logs and pending `task_outbox` rows.
- **Liveness rejects after selecting MiniFASNet:** check external source, filenames, mounted weights and 3–10 uploaded frames. Missing models cannot silently approve.
- **Phone camera is unavailable:** use an HTTPS origin accessible from both devices. `localhost` points to the phone itself when opened on a phone.
- **Phone link expired or upload failed:** generate a new single-use link from the desktop.
- **Approval is always referred to review:** default liveness is heuristic; also inspect missing cross-document fields, OCR confidence and registry rules. Do not lower thresholds merely to obtain a green result.
- **Health returns 503:** PostgreSQL or Redis is unavailable. This endpoint checks dependencies, not model readiness or accuracy.

## Integration tests

Use a dedicated migrated PostgreSQL database whose name contains `test`. Never point the integration suite at a live application database.

```powershell
$env:DATABASE_URL = 'postgresql+asyncpg://test_user:test_pass@localhost:5544/idv_test'
$env:JWT_SECRET_KEY = 'synthetic-test-signing-key-at-least-32-characters'
$env:IDV_INTEGRATION_TESTS = '1'
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m pytest tests -q
```

The tests insert synthetic users/applications. Use a disposable database. Unit tests and browser tests do not download ML models.

## Showcase artifacts

With the frontend running and Playwright installed:

```powershell
node scripts/capture_showcase.mjs
```

`SHOWCASE_URL` can override the default `http://127.0.0.1:5173/demo`. The script captures synthetic screenshots and a short WebM recording. It never uses private applications or documents.
