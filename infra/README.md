# Deployment (infra/)

KnowledgeMind ships two deploy targets, wired to GitHub Actions:

- **Hugging Face Spaces** — the full app (FastAPI backend **+** the built React SPA, one container). Best for the ML-heavy backend (16 GB free RAM).
- **Vercel** — the React front-end only, pointed at the HF Space API. Optional; the HF Space already serves the UI.

```
infra/
├── Dockerfile              # HF Spaces image (multi-stage: node build -> python run on :7860)
├── .dockerignore           # copied to repo root at deploy time
├── huggingface/README.md   # HF Space config header (sdk: docker, app_port: 7860)
└── vercel.json             # Vercel build config for frontend/
```

## Access lock (static auth)

The app is locked by a shared **access key**: every `/api/*` request must send
`X-Access-Key: <ACCESS_KEY>`; the React UI shows a login screen and stores the
key locally. If `ACCESS_KEY` is unset the API is open (local dev). Set it as a
secret on each host. The key is never committed or baked into the build.

## Required GitHub repo secrets

| Secret | Used by | Notes |
|--------|---------|-------|
| `HF_TOKEN` | HF deploy | A Hugging Face write token. |
| `HF_SPACE_ID` | HF deploy | e.g. `your-username/knowledgemind`. |
| `VERCEL_TOKEN` | Vercel deploy | Vercel access token. |
| `VERCEL_ORG_ID` | Vercel deploy | From `.vercel/project.json` after `vercel link`. |
| `VERCEL_PROJECT_ID` | Vercel deploy | Same. |

## Host environment variables / secrets

**Hugging Face Space** (Settings → Variables and secrets): `ACCESS_KEY` (required to lock),
`GROQ_API_KEY`, optionally `ALLOWED_ORIGINS` (your Vercel URL), `TAVILY_API_KEY`, `SLACK_BOT_TOKEN`.

**Vercel** (Project → Settings → Environment Variables): `VITE_API_BASE` = your HF Space URL
(e.g. `https://your-username-knowledgemind.hf.space`). The access key is **not** stored on
Vercel — users enter it at the login screen.

## One-time setup

1. **HF Space:** create a Space (SDK: Docker). Add `HF_TOKEN` + `HF_SPACE_ID` repo secrets. Set `ACCESS_KEY` + `GROQ_API_KEY` Space secrets.
2. **Vercel (optional):** `vercel link` the repo, copy the org/project IDs into repo secrets, set `VITE_API_BASE`, and add the Vercel URL to the Space's `ALLOWED_ORIGINS`.
3. Push to `main` → both workflows deploy.

## Run locally

```bash
# Backend (open, no key) + built SPA:
cd frontend && npm install && npm run build && cd ..
.venv/bin/python launcher.py            # http://127.0.0.1:8000

# Or hot-reload dev (two terminals):
.venv/bin/uvicorn api.main:app --reload # backend on :8000
cd frontend && npm run dev              # Vite on :5173 (proxies /api -> :8000)

# To test the lock locally:
ACCESS_KEY=secret123 .venv/bin/python launcher.py
```
