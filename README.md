# Medi

Medi is a home medical health assistant based on MSD Manuals Home Edition.

The current repository contains:

- `frontend/`: Next.js frontend.
- `backend/`: FastAPI backend matching the current frontend API contract.

## Backend Contract

The frontend contract is defined by `frontend/src/lib/api/types.ts`,
`frontend/src/lib/api/client.ts`, `frontend/src/lib/api/handlers.ts`, and
`frontend/API_CONTRACT.md`.

The backend implements the same contract:

- Cookie session auth with `medi_session`, compatible with frontend
  `credentials: "include"` requests.
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

- SQLite is used for first-stage local integration.
- MSD knowledge data in `backend/app/data/seed_knowledge.json` is sample-only.
- Qwen and OCR are isolated behind service adapters for later replacement.
- Red-flag symptom handling is deterministic and independent from model output.
