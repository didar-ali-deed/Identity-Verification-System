# Run and check the project

## Windows / Docker Desktop

Start Docker Desktop, then open PowerShell:

```powershell
cd E:\idv\Identity-Verification-System
.\scripts\start.ps1
```

The script initializes a private root `.env` if missing, builds containers and waits for health checks. Existing data is retained. First inference downloads model files.

- App: http://localhost:8080
- Synthetic demonstration: http://localhost:8080/demo
- Backend docs: http://localhost:18000/api/docs

```powershell
docker compose ps
docker compose logs --tail 50 backend celery-worker celery-beat
docker compose exec backend python -m app.cli create-admin --email reviewer@example.com --name Reviewer
```

The administrator command prompts for a password. Do not publish `.env`, database dumps, personal images or credentials.

## Test the workflow

Register or sign in. Use **Reset verification** for a new attempt; completed results are retained until an explicit reset. Upload clear, upright documents, review OCR and capture a fresh selfie. Watch the result page until processing finishes. Inspect the stage evidence instead of assuming matching text implies authentic identity.

The samples linked on the upload page are visibly fictional, deliberately invalid OCR fixtures. They are not an approval test. Default heuristic liveness cannot grant automatic approval. Missing MRZ or unavailable/failed biometric evidence may still cause review or rejection after the OCR fix.

## Phone camera over HTTPS

If cloudflared is installed:

```powershell
.\scripts\start-phone.ps1
```

Open the printed HTTPS address on your phone and allow camera access. For QR handoff, open that same address on the computer before selecting **Use phone**. Keep Docker, the computer and the tunnel terminal running. Ctrl+C stops the tunnel. Each restart generates a new temporary public URL; localhost on the phone is the phone itself. This is a development tunnel, not a production deployment.

## Checks and stopping

```powershell
.venv\Scripts\python.exe -m pytest backend\tests -q
.venv\Scripts\python.exe -m ruff check backend\app backend\tests
cd frontend
npm ci
npm run lint
npm run build
npx playwright install chromium
npx playwright test
```

Backend dependencies must be installed first; see [development setup](development.md). PostgreSQL integration tests need a dedicated migrated test database and `IDV_INTEGRATION_TESTS=1`. Never point integration tests at your app database.

From the repository root, `docker compose down` stops the app and retains stored data. Avoid `down -v` unless you intend to delete volumes. Review [the improvement plan](improvement-plan.md) for remaining model and production work.
