# Medi

Medi is a home medical health assistant based on the MSD Manuals Home Edition. This repository currently contains the first-stage backend implementation for a China-mainland web product: user authentication, personal health profile tags, MSD-based knowledge retrieval, cited RAG answers, and medical report upload/analysis contracts.

The product is positioned as a health education and safe triage assistant, not a diagnosis, prescription, or treatment system. All AI output must be grounded in authorized MSD knowledge blocks and must provide citations back to the original topic pages.

## First-stage scope

The first stage implements the backend capabilities needed by the frontend pages listed in the project requirements:

- User registration and login.
- Personal health profile creation and update.
- Rule-based user tag generation, such as age group, sex, allergy, chronic condition, and current medication tags.
- Medical question submission with profile-aware knowledge retrieval.
- RAG-style answer generation with required MSD citations.
- Red-flag triage override for high-risk symptoms such as chest pain, dyspnea, loss of consciousness, severe trauma, major bleeding, and anaphylaxis.
- Medical report upload contract for JPG, JPEG, PNG, and PDF files.
- Report analysis result contract with extracted indicators, status, explanations, suggestions, and citations.
- API contract documentation for frontend/backend integration.

## Backend location

The backend code is under [`backend/`](backend/).

```text
backend/
  app/
    api/            FastAPI routes and authentication dependencies
    core/           configuration, token security, unified responses
    models/         Pydantic request and response models
    services/       auth, profile, knowledge retrieval, RAG, report services
    data/           local seed knowledge for integration testing
  contracts/        TypeScript API types for frontend integration
  docs/             API contract and MSD text-tag schema
```

## Architecture

The planned production architecture follows the project requirements:

- FastAPI exposes all `/api/v1` backend routes.
- PostgreSQL stores users, profiles, tags, report records, MSD page metadata, sections, knowledge chunks, and audit logs.
- Milvus stores section-level or chunk-level embedding vectors.
- Qwen API handles answer generation, query rewriting, reranking, and report explanation after citation validation.
- OCR extracts report fields, units, reference ranges, and sampling time.
- MSD Manuals Home Edition is the only medical knowledge source.

For the current first-stage implementation, SQLite is used as a local development substitute so frontend/backend integration can start immediately. The service boundaries are already separated so PostgreSQL, Milvus, Qwen, and OCR can replace the current local adapters later without changing the public API contract.

## Implemented API modules

All responses use a unified shape:

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

Implemented endpoints:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `PUT /api/v1/profile`
- `GET /api/v1/profile`
- `GET /api/v1/knowledge/search`
- `POST /api/v1/chat/query`
- `POST /api/v1/reports/analyze`
- `GET /api/v1/reports/{report_id}`
- `GET /api/v1/health`

Detailed request and response examples are documented in [`backend/docs/api_contract.md`](backend/docs/api_contract.md).

## MSD content schema

MSD pages should be imported at topic-page, section, and knowledge-block levels. The first-stage minimum fields are:

- `source_url`
- `topic_type`
- `title`
- `category_path`
- `section_title`
- `plain_text` or `chunk_text`
- `authors`
- `reviewers`
- `revised_at`
- `version_label`
- `content_hash`
- `citation_anchor`

The full suggested text-tag schema is in [`backend/docs/msd_text_schema.md`](backend/docs/msd_text_schema.md). It covers page metadata, section metadata, chunk metadata, multimedia assets, and laboratory indicator records.

## Run locally

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

After startup:

- Swagger UI: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/v1/health`

## Current implementation notes

- The included knowledge data is sample-only and must be replaced by authorized MSD content before any real medical use.
- Qwen integration is represented by a deterministic adapter placeholder in `backend/app/services/qwen_client.py`.
- OCR integration is represented by a report parsing placeholder in `backend/app/services/report_service.py`.
- Red-flag symptom handling is deterministic and independent from the LLM path.
- Uploaded reports are treated as sensitive personal information; production deployment must add the planned consent, encryption, retention, export, deletion, and audit controls.

## Validation completed

Local validation was run before publishing:

- Parsed all backend Python files with Python `ast.parse`.
- Ran a service-layer smoke test covering registration, profile tag generation, knowledge retrieval, RAG query output, and citation return.
