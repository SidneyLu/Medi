# Frontend API Contract

This backend follows the current frontend contract in `frontend/src/lib/api/client.ts`,
`types.ts`, and `handlers.ts`.

## Common Rules

- API prefix: `/api/v1`
- Auth: HttpOnly cookie session named `medi_session`
- Frontend requests use `credentials: "include"`
- CORS must allow credentials and concrete origins, not `*`
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

- `POST /api/v1/auth/register` -> `201`, returns `User`, sets cookie
- `POST /api/v1/auth/login` -> returns `User`, sets cookie
- `POST /api/v1/auth/logout` -> returns `null`, clears cookie
- `GET /api/v1/auth/me` -> returns `User`

`User`:

```ts
{ user_id: string; email: string; nickname: string }
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

This contract intentionally differs from the early planning example:

- Auth returns `User` and uses cookies, not access tokens in JSON.
- Chat uses conversations and messages, not single-shot `/chat/query`.
- Report analysis is split into OCR confirmation and interpretation.
