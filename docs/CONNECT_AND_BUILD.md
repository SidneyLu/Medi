# Medi Connection And Build Guide

This guide explains how to connect the Next.js frontend with the FastAPI backend,
how to build each side, and what was verified locally.

## 1. Repository Layout

```text
Medi/
  frontend/        Next.js app
  backend/         FastAPI app
  docs/            connection and build guides
```

Current API source of truth:

- Frontend client: `frontend/src/lib/api/client.ts`
- Frontend types: `frontend/src/lib/api/types.ts`
- Backend contract notes: `backend/docs/api_contract.md`
- Backend routes: `backend/app/api/routes/`

## 2. Authentication And API Connection

The current code uses Bearer tokens, not cookie sessions.

Flow:

1. Frontend calls `POST /api/v1/auth/login` or `POST /api/v1/auth/register`.
2. Backend returns an `AuthSession` object containing:
   - `user_id`
   - `email`
   - `nickname`
   - `access_token`
   - `token_type: "bearer"`
   - `expires_in`
3. Frontend stores `access_token` in `localStorage`.
4. Frontend sends protected requests with:

```text
Authorization: Bearer <access_token>
```

Backend routes are mounted under:

```text
/api/v1
```

## 3. Local Development: Backend

Open a terminal at the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend checks:

```powershell
curl http://127.0.0.1:8000/api/v1/health
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

Important dependency:

- `python-multipart` is required because `POST /api/v1/reports/analyze` accepts `multipart/form-data`.

## 4. Local Development: Frontend

Open a second terminal at the repository root:

```powershell
cd frontend
npm ci
```

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_MODE=real
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Start the frontend:

```powershell
npm run dev
```

Open:

```text
http://127.0.0.1:3000
```

Why `NEXT_PUBLIC_API_BASE_URL` is needed:

- `frontend/src/lib/api/client.ts` builds requests as `${NEXT_PUBLIC_API_BASE_URL}/api/v1/...`.
- When frontend and backend run on different ports, set it to `http://127.0.0.1:8000`.
- If frontend and backend are served from the same origin in production, this value can be empty.

## 5. Production Build

Backend does not need a compile step. A typical production command is:

```powershell
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Frontend production build:

```powershell
cd frontend
npm ci
npm run build
npm run start
```

## 6. Quick API Smoke Test

After backend starts, verify login and protected access:

```powershell
$body = @{ email = "demo@example.com"; password = "Password123" } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/auth/register" `
  -ContentType "application/json" `
  -Body $body

$token = $login.data.access_token
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8000/api/v1/auth/me" `
  -Headers @{ Authorization = "Bearer $token" }
```

Expected:

- register returns HTTP `201`
- response envelope has `code: 0`
- `data.access_token` exists
- `/auth/me` returns the same user

## 7. Verified Locally

Verified on 2026-07-16:

- Connected to `SidneyLu/Medi` and fast-forwarded local `main`.
- Confirmed PR #2 had been merged.
- Confirmed the current frontend uses Bearer tokens via `Authorization`.
- Installed missing backend upload dependency `python-multipart`.
- Imported the FastAPI app successfully after installing `python-multipart`.
- Ran a FastAPI `TestClient` HTTP smoke test:
  - `POST /api/v1/auth/register`
  - `GET /api/v1/auth/me`
  - `PUT /api/v1/profile`
  - `POST /api/v1/chat/conversations`
  - `POST /api/v1/chat/conversations/{id}/messages`
  - `POST /api/v1/reports/analyze`
  - `POST /api/v1/reports/{id}/interpret`
- Service-layer smoke test also passed for auth, profile tags, chat, report OCR confirmation, interpretation, and delete flow.

Frontend build status on this machine:

- `npm ci` did not complete because the local npm/network certificate chain failed with `UNABLE_TO_VERIFY_LEAF_SIGNATURE`.
- Because dependencies were incomplete, `npm run build` failed with `next is not recognized`.
- This is an environment/certificate issue, not a TypeScript or Next.js build error from the source code.

## 8. Troubleshooting

### FastAPI says `python-multipart` is missing

Run:

```powershell
cd backend
pip install -r requirements.txt
```

or:

```powershell
pip install python-multipart
```

### `npm ci` fails with `UNABLE_TO_VERIFY_LEAF_SIGNATURE`

This means npm cannot verify the TLS certificate chain for the configured
registry. Safer fixes:

```powershell
npm config get registry
npm config set registry https://registry.npmjs.org/
```

If your network uses a corporate or campus HTTPS proxy, install the proxy CA
certificate and configure npm with:

```powershell
npm config set cafile C:\path\to\proxy-ca.pem
```

Avoid making `strict-ssl=false` the default project instruction. It can be used
only as a temporary local diagnostic choice when the network owner explicitly
requires it.

### Frontend cannot connect to backend

Check `frontend/.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Restart `npm run dev` after changing `.env.local`.

Check backend health:

```powershell
curl http://127.0.0.1:8000/api/v1/health
```

Check browser DevTools:

- Request URL should start with `http://127.0.0.1:8000/api/v1`.
- Protected requests should include `Authorization: Bearer <token>`.

### `python -m venv` fails during `ensurepip`

Use an existing Python with pip, repair the Python installation, or install
Python from python.org with pip enabled. The backend can still be started from a
working Python environment if `requirements.txt` dependencies are installed.

