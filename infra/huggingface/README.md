---
title: KnowledgeMind
emoji: 🧠
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# KnowledgeMind

Privacy-aware personal agent (FastAPI backend + React front-end), served on port 7860.

## Required Space secrets (Settings → Variables and secrets)

| Secret | Purpose |
|--------|---------|
| `ACCESS_KEY` | **Locks the app.** Every `/api/*` request must send this as `X-Access-Key`; users enter it on the login screen. Without it set, the app is open. |
| `GROQ_API_KEY` | Enables the live assistant + cloud routing. |

## Optional

| Secret | Purpose |
|--------|---------|
| `ALLOWED_ORIGINS` | Comma-separated origins allowed via CORS (only needed if the front-end is hosted on a different origin). |
| `TAVILY_API_KEY` | Web-search tool. |
| `SLACK_BOT_TOKEN` | Live Slack connector (otherwise mock data). |

This Space is deployed automatically by the GitHub Actions workflow
`deploy-huggingface.yml`. The app uses ephemeral storage under `/tmp` and
re-seeds demo data on startup.
