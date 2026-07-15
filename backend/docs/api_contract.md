# Frontend API Contract

This backend follows the current frontend contract in `frontend/src/lib/api/client.ts`,
`types.ts`, and `handlers.ts`.

## Common Rules

- API prefix: `/api/v1`
- Auth: Bearer access token in `Authorization` header
- Login/register return `access_token`, `token_type: "bearer"`, `expires_in`
- Frontend stores the token (e.g. `localStorage`) and sends `Authorization: Bearer <token>`
- Cookie sessions are not used
- JSON response envelope:

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "request_id": "uuid"
}
```

Error response example:

```json
{
  "code": 404,
  "message": "Conversation not found",
  "data": null,
  "request_id": "uuid",
  "error": { "type": "not_found" }
}
```

## Auth

- `POST /api/v1/auth/register` -> `201`, returns `AuthSession`
- `POST /api/v1/auth/login` -> returns `AuthSession`
- `POST /api/v1/auth/logout` -> returns `null` (client clears local token)
- `GET /api/v1/auth/me` -> returns `User` (requires Bearer token)

`User`:

```ts
{ user_id: string; email: string; nickname: string }
```

`AuthSession`:

```ts
{
  user_id: string;
  email: string;
  nickname: string;
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}
```

## Profile

- `GET /api/v1/profile` -> `{ profile: Profile | null; tags: string[] }`
- `PUT /api/v1/profile` -> saves full `Profile`, regenerates tags, returns profile and tags

## Chat

The frontend is conversation-based.

- `GET /api/v1/chat/conversations`
- `POST /api/v1/chat/conversations`
- `GET /api/v1/chat/conversations/{id}`
- `POST /api/v1/chat/conversations/{id}/messages`

`POST .../messages` request:

```json
{
  "question": "I often feel dizzy recently. What could be the reason?",
  "use_profile": true
}
```

Response `data` is the assistant-side `ChatMessage`. The backend also stores the
user message in the conversation history.

## Reports

The frontend report flow is staged: upload/OCR, user confirmation, interpretation.

- `GET /api/v1/reports`
- `POST /api/v1/reports/analyze` -> `202`, returns `Report` with `status: "needs_confirmation"`
- `GET /api/v1/reports/{id}`
- `PATCH /api/v1/reports/{id}/items`
- `POST /api/v1/reports/{id}/interpret` -> returns completed interpreted report
- `DELETE /api/v1/reports/{id}`

`PATCH .../items` request:

```json
{
  "items": []
}
```

## Compatibility Notes

This contract intentionally differs from the early cookie-session approach:

- Auth returns Bearer `access_token` in JSON; clients send `Authorization: Bearer ...`
- Chat uses conversations and messages, not single-shot `/chat/query`.
- Report analysis is split into OCR confirmation and interpretation.
