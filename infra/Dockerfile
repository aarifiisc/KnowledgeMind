# KnowledgeMind — Hugging Face Spaces (Docker SDK). Listens on :7860.
# The deploy workflow (.github/workflows/deploy-huggingface.yml) copies this
# file plus infra/.dockerignore and infra/huggingface/README.md to the Space
# root, where Docker builds from the repo root as context.

# --- Stage 1: build the React frontend --------------------------------------
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python runtime ------------------------------------------------
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/tmp/hf \
    XDG_CONFIG_HOME=/tmp/kmconfig
WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements.txt \
 && python -m spacy download en_core_web_sm

# App source (frontend/ source + heavy dirs excluded via .dockerignore);
# the built SPA is copied from the frontend stage.
COPY . .
COPY --from=frontend /app/frontend/dist ./frontend/dist

EXPOSE 7860
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860"]
