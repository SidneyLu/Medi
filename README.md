# Medi

Medi is a home medical health assistant based on MSD Manuals Home Edition.

The current repository contains:

- `frontend/`: Next.js frontend.
- `backend/`: FastAPI backend matching the current frontend API contract.

## One-click Local Run

On Windows, start both backend and frontend from the repository root:

```powershell
.\start-dev.ps1
```

Or double-click `start-dev.bat`.

Application data is stored in PostgreSQL. Before running the backend, make sure
`DATABASE_URL` in `backend/.env` points to a reachable PostgreSQL database. If
Docker is available, the bundled development database can be started with:

```powershell
cd backend
docker compose -f docker-compose.knowledge.yml up -d postgres
cd ..
```

The launcher starts:

- Backend: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- Frontend: `http://127.0.0.1:3000`

Useful options:

```powershell
.\start-dev.ps1 -BackendPort 8001 -FrontendPort 3001
.\start-dev.ps1 -SkipInstall
.\start-dev.ps1 -CheckOnly
```

## Backend Contract

The frontend contract is defined by `frontend/src/lib/api/types.ts`,
`frontend/src/lib/api/client.ts`, `frontend/src/lib/api/handlers.ts`, and
`backend/docs/api_contract.md`.

The backend implements the same contract:

- Bearer token auth. Login/register return `access_token`; protected requests
  send `Authorization: Bearer <token>`.
- Unified response envelope with `code`, `message`, `data`, and `request_id`.
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/profile`
- `PUT /api/v1/profile`
- `GET /api/v1/chat/conversations`
- `POST /api/v1/chat/conversations`
- `GET /api/v1/chat/conversations/{id}`
- `POST /api/v1/chat/conversations/{id}/messages`
- `GET /api/v1/reports`
- `POST /api/v1/reports/analyze`
- `GET /api/v1/reports/{id}`
- `PATCH /api/v1/reports/{id}/items`
- `POST /api/v1/reports/{id}/interpret`
- `DELETE /api/v1/reports/{id}`

More backend details are in `backend/README.md` and
`backend/docs/api_contract.md`.

Connection and build steps are in `docs/CONNECT_AND_BUILD.md`.

## Backend Local Run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Swagger: `http://127.0.0.1:8000/docs`

## Current Backend Notes

- PostgreSQL stores users, profiles, chat history, reports, and audit logs.
- SQLite is kept only for local seed-knowledge fallback.
- MSD knowledge data in `backend/app/data/seed_knowledge.json` is sample-only.
- Qwen and OCR are isolated behind service adapters for later replacement.
- Red-flag symptom handling is deterministic and independent from model output.
