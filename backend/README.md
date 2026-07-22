# Medi Backend

FastAPI backend for the current Medi frontend contract.

## Run Locally

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Open:

- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/v1/health`

## Implemented Frontend Contract

The frontend uses Bearer tokens. Login/register return `access_token` in JSON;
protected routes require `Authorization: Bearer <token>`.

Implemented endpoints:

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

Full details are in `docs/api_contract.md`.

## Architecture

```text
app/
  api/            FastAPI routes and Bearer auth dependency
  core/           settings, response envelope, signed session token helpers
  models/         Pydantic models matching the frontend TypeScript types
  services/       auth, profile, knowledge retrieval, chat/RAG, reports
  data/           sample-only knowledge chunks for local integration
contracts/        TypeScript API contract mirror
docs/             API contract and MSD text schema
```

SQLite is used for first-stage local integration. Production replacement points:

- PostgreSQL for users, profiles, reports, conversations, MSD metadata, and audit logs.
- Milvus for chunk-level vector retrieval.
- Qwen API for answer generation, query rewriting/reranking, and report interpretation.
- OCR engine for reliable medical report extraction.

## Safety Boundaries

- MSD Manuals Home Edition is the intended sole medical knowledge source.
- The included seed knowledge is sample-only and must not be used as medical content.
- Chat answers are grounded in retrieved chunks. If no evidence is found, the backend refuses to invent medical content.
- Red-flag rules are deterministic and independent from the model path.
- Report interpretation is educational only and must not output diagnosis, prescription, or individualized treatment conclusions.
