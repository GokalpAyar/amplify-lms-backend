## Amplify LMS Backend

This FastAPI service powers Amplify LMS, including user/auth flows, assignment management, and Whisper-powered speech transcription.

### 1. Environment Variables

Create `backend/.env` from `.env.example` and fill in the secrets (these same keys should be configured on Vercel):

| Variable | Description |
| --- | --- |
| `DATABASE_URL` | Production connection string. When omitted the app falls back to `backend/amplify.db` (SQLite) for local dev. |
| `OPENAI_API_KEY` | Server-side key for the Whisper API. **Never expose this in frontend code.** |
| `OPENAI_WHISPER_MODEL` | Whisper model name (defaults to `whisper-1`). |
| `JWT_SECRET` | Secret used to sign JWTs. |
| `FRONTEND_ORIGINS` | Comma-separated list of allowed origins for CORS (`https://your-vercel-app.vercel.app,https://localhost:5173`). |
| `FRONTEND_ORIGIN_REGEX` (optional) | Regex variant when you must allow a wildcard domain. |

For the Vite frontend, copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_URL` (e.g. `https://your-api.onrender.com`).

### 2. Local Development

```bash
# Terminal 1 – API
cd backend
uvicorn main:app --reload --port 8000

# Terminal 2 – Frontend
cd frontend
npm install
npm run dev
```

### 3. Whisper Endpoint

- `POST /api/transcribe`: multipart form upload (`file`) that proxies audio to the OpenAI Whisper API and returns `{ transcription, status }`.
- `/speech/upload-audio/` remains for backward compatibility but new clients should prefer `/api/transcribe`.

### 4. Deployment on Vercel

- `vercel.json` in the repo root now only configures a static rewrite so Vercel serves the Vite build from `frontend/dist`.
- Set the frontend’s `VITE_API_URL` in the Vercel dashboard so the React app can talk to the externally hosted FastAPI service.
- Optionally set `VITE_DEV_PROXY_TARGET` locally to point the Vite dev proxy at a remote API.

### 5. Key Routes

- `POST /assignments/`
- `GET /assignments/`
- `POST /responses/`
- `GET /responses/?assignment_id=...`
- `POST /api/transcribe`

See the interactive docs at `/docs` for the full schema.
