# Deployment (infra/)

KnowledgeMind deploys to **Hugging Face Spaces** — the full app (FastAPI backend
**+** the built React SPA) in a single Docker container, wired to GitHub Actions.
Best for the ML-heavy backend (free CPU tier, 16 GB RAM).

```
infra/
├── Dockerfile              # HF Spaces image (multi-stage: node build -> python run on :7860)
├── .dockerignore           # copied to repo root at deploy time
└── huggingface/README.md   # HF Space config header (sdk: docker, app_port: 7860)
```

## Access lock (static auth)

The app is locked by a shared **access key**: every `/api/*` request must send
`X-Access-Key: <ACCESS_KEY>`; the React UI shows a login screen and stores the
key locally. If `ACCESS_KEY` is unset the API is open (local dev). Set it as a
Space secret. The key is never committed or baked into the build.

## Required GitHub repo secrets

| Secret | Used by | Notes |
|--------|---------|-------|
| `HF_TOKEN` | HF deploy | A Hugging Face **write** token. |
| `HF_SPACE_ID` | HF deploy | e.g. `your-username/knowledgemind`. |

## Host environment variables / secrets

**Hugging Face Space** (Settings → Variables and secrets): `ACCESS_KEY` (required to lock),
`GROQ_API_KEY`, optionally `TAVILY_API_KEY`, `SLACK_BOT_TOKEN`. `ALLOWED_ORIGINS` is only
needed if you serve the front-end from a different origin — the Space serves it same-origin.

## One-time setup

1. **HF Space:** create a Space (SDK: Docker). Add `HF_TOKEN` + `HF_SPACE_ID` repo secrets. Set `ACCESS_KEY` + `GROQ_API_KEY` Space secrets.
2. Push to `main` → the workflow builds the container and deploys.

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
