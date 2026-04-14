# Identity Verification System (IDV)

A production-grade **Identity Verification System** that performs forensic-level document verification through a 10-stage AI pipeline. Designed for visa processing, onboarding, and compliance workflows.

---

## What It Does

Users submit their identity documents (passport, national ID) and a live selfie. The system runs them through a 10-stage verification pipeline that checks document authenticity, extracts and cross-validates all fields, screens against watchlists, computes a biometric similarity score, and produces an automated decision — **Approved**, **Manual Review**, or **Rejected**.

Admins review flagged applications through a dashboard with full pipeline breakdown, stage-by-stage results, and channel scores.

---

## 10-Stage Verification Pipeline

| Stage | Name | Description |
|-------|------|-------------|
| 0 | Document Acceptance Gate | Classifies document type (TD1/TD2/TD3), validates issuing country against approved list, checks document class eligibility |
| 1 | Liveness & Anti-Spoofing | Detects screen replay (FFT moiré), printout attacks (halftone), pixel tampering (ELA + ORB), selfie liveness (LBP texture) |
| 2 | Dual-Zone Field Extraction | Extracts MRZ (ICAO 9303 check digits) and VIZ fields from passport and national ID front/back |
| 3 | Normalization & Cross-Zone Consistency | Normalizes dates, names (ICAO transliteration), ID numbers; cross-validates VIZ vs MRZ; hard-fails on expired documents |
| 4 | Fraud & Watchlist Screening | Exact ID number + fuzzy name match against watchlist; duplicate application detection; velocity limiting; form data consistency |
| 5 | 5-Channel Similarity Scoring | Biometric face (DeepFace), ID number match, name Jaccard+Levenshtein, father name edit distance, DOB binary match |
| 6 | Weighted Score Synthesis | `0.40A + 0.25B + 0.15C + 0.10D + 0.10E` → weighted total [0.0, 1.0] |
| 7 | Hard-Rule Override Layer | 11 rules evaluated; worst outcome wins — id mismatch, liveness fail, watchlist hit all trigger hard overrides |
| 8 | Decision Matrix | ≥ 0.90 → Approved · 0.75–0.89 → Manual Review · < 0.75 → Rejected |
| 9 | Result & Audit Trail | Persists immutable pipeline result, updates application status, stores per-document metadata |

**Hard-fail bypass:** Stages 0, 1, and 3 can hard-fail and skip directly to Stage 7→8→9, bypassing scoring when documents are fundamentally invalid.

---

## Similarity Channels

| Channel | Signal | Weight |
|---------|--------|--------|
| A | Biometric face match (selfie vs passport + selfie vs ID) | 40% |
| B | ID number exact match | 25% |
| C | Full name — Jaccard token overlap + normalized Levenshtein | 15% |
| D | Father's name edit distance | 10% |
| E | Date of birth binary match + single-digit transposition detection | 10% |

---

## Tech Stack

### Backend
- **FastAPI** — async REST API (Python 3.12)
- **PostgreSQL** — primary database with SQLAlchemy ORM + Alembic migrations
- **Redis** — session cache and Celery broker
- **Celery** — async task queue for pipeline execution
- **EasyOCR** — multi-language OCR for field extraction
- **DeepFace** — biometric face similarity (VGG-Face / ArcFace backends)
- **face_recognition** — face detection and cropping
- **OpenCV / NumPy** — liveness detection (FFT, ELA, LBP, ORB)
- **structlog** — structured JSON logging

### Frontend
- **React 18** with TypeScript (strict mode)
- **Tailwind CSS** + shadcn/ui — component library
- **React Query** — server state management
- **React Router v6** — routing
- **Zustand** — auth state
- **Axios** — HTTP client with JWT interceptors
- **react-webcam** — live selfie capture

### Infrastructure
- **Docker** + **Docker Compose** — full stack containerization
- **Nginx** — reverse proxy
- **GitHub Actions** — CI/CD pipeline

---

## Features

### User Flow
- Register / login with JWT authentication (access + refresh token rotation)
- Submit IDV application with document type selection
- Upload passport or national ID photo
- Capture live selfie via webcam
- Track application status through 10-stage progress view

### Admin Dashboard
- View all applications with status filters and pagination
- Full pipeline breakdown per application — stage results, flags, reason codes
- 5-channel similarity scores with visual bar chart
- Weighted total score and final decision badge
- Approve / reject applications with audit log
- Manage approved countries, document class rules, and watchlist entries

### Security
- Passwords hashed with bcrypt (12 rounds)
- JWT tokens — 30 min access, 7 day refresh with rotation
- Rate limiting on auth endpoints
- File upload validation — JPEG/PNG only, 10 MB max, dimension check
- CORS restricted to known origins
- All queries parameterized via SQLAlchemy ORM

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `users` | Authentication, roles (user/admin) |
| `idv_applications` | Application lifecycle and pipeline decision |
| `documents` | Uploaded files, OCR data, normalized fields, liveness scores |
| `face_verifications` | Selfie vs document face match results |
| `pipeline_results` | Immutable per-stage JSON results, channel scores, flags |
| `watchlist_entries` | Fraud screening — ID numbers and names |
| `approved_countries` | Country-level acceptance gate |
| `document_class_rules` | Per-country document type eligibility |
| `audit_logs` | Admin action trail |

---

## API Endpoints

```
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh

POST   /api/v1/idv/submit
GET    /api/v1/idv/status
POST   /api/v1/idv/upload-document
POST   /api/v1/idv/upload-selfie
GET    /api/v1/idv/pipeline-result

GET    /api/v1/admin/applications
GET    /api/v1/admin/applications/:id
PATCH  /api/v1/admin/applications/:id
GET    /api/v1/admin/stats
GET    /api/v1/admin/pipeline/countries
POST   /api/v1/admin/pipeline/countries
DELETE /api/v1/admin/pipeline/countries/:code
GET    /api/v1/admin/pipeline/rules
POST   /api/v1/admin/pipeline/rules
DELETE /api/v1/admin/pipeline/rules/:id
GET    /api/v1/admin/pipeline/watchlist
POST   /api/v1/admin/pipeline/watchlist
DELETE /api/v1/admin/pipeline/watchlist/:id

GET    /api/v1/health
```

---

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Node.js 18+ (for local frontend dev)
- Python 3.12+ (for local backend dev)

### Run with Docker

```bash
cp .env.example .env        # fill in your secrets
docker-compose up --build
```

App available at `http://localhost` (Nginx) or:
- Frontend: `http://localhost:5173` (dev)
- Backend API: `http://localhost:8000`
- API Docs: `http://localhost:8000/docs`

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

### Environment Variables

```env
DATABASE_URL=postgresql+asyncpg://idv_user:idv_password@localhost:5432/idv_db
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=<generate with: openssl rand -hex 32>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
UPLOAD_DIR=./uploads
MAX_FILE_SIZE_MB=10
FACE_SIMILARITY_THRESHOLD=0.6
FRAUD_SCORE_THRESHOLD=0.7
PIPELINE_MODE=god
PIPELINE_PASS_THRESHOLD=0.90
PIPELINE_REVIEW_THRESHOLD=0.75
```

---

## Project Structure

```
project/
├── backend/
│   ├── app/
│   │   ├── api/              # Route handlers (idv, admin, auth)
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── pipeline/     # 10-stage pipeline (stage_0 → stage_9)
│   │   │   ├── idv_service.py
│   │   │   ├── ocr_service.py
│   │   │   ├── face_service.py
│   │   │   └── fraud_service.py
│   │   └── tasks/            # Celery async tasks
│   └── alembic/              # Database migrations
├── frontend/
│   └── src/
│       ├── api/              # React Query hooks
│       ├── components/       # UI components + PipelineBreakdown
│       ├── pages/            # IDVSubmission, IDVStatus, AdminDashboard
│       └── types/            # TypeScript interfaces
├── nginx/
│   └── nginx.conf
└── docker-compose.yml
```

---

## License

MIT
# Identity-Verification-System
