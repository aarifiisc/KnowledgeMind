# build_windows.spec
# ------------------
# PyInstaller spec for building KnowledgeMind.exe on Windows.
#
# This packages the FastAPI backend (api.main:app) + the built React SPA
# (frontend/dist) into a single distributable. Ollama is NOT bundled (users
# install it separately from ollama.com).
#
# Prerequisites (run BEFORE pyinstaller):
#   pip install pyinstaller
#   pip install -r requirements.txt
#   python -m spacy download en_core_web_sm
#   cd frontend && npm install && npm run build && cd ..   # builds frontend/dist
#
# Usage:
#   pyinstaller build_windows.spec --clean --noconfirm
#
# Output: dist/KnowledgeMind/KnowledgeMind.exe  (folder bundle, --onedir)

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ---------------------------------------------------------------------------
# Data files (non-Python assets read at runtime). All app paths are resolved
# relative to each module's __file__, so the bundled layout must mirror the
# source tree under _MEIPASS (e.g. api/main.py -> ../frontend/dist).
# ---------------------------------------------------------------------------
datas = []
datas += collect_data_files("spacy")
datas += collect_data_files("en_core_web_sm")     # spaCy English model
datas += collect_data_files("chromadb")           # RAG vector store assets
datas += collect_data_files("eval")               # eval golden fixtures, if any

datas += [
    ("frontend/dist", "frontend/dist"),   # built React SPA served by FastAPI
    ("hermes_jobs", "hermes_jobs"),       # proactive runtime job specs (read at runtime)
    ("hermes_skills", "hermes_skills"),   # proactive runtime skills (read at runtime)
    ("data", "data"),                     # mock data for offline mode
    ("projmgmt", "projmgmt"),             # Project Advisor sub-app: imported dynamically
                                          # (sys.path.insert + `import main`), so PyInstaller
                                          # cannot trace it -- ship the whole tree as data.
]

# ---------------------------------------------------------------------------
# Hidden imports. uvicorn loads the app by the STRING "api.main:app", so the
# entire KM package graph is invisible to static analysis and must be forced in
# explicitly -- without this the exe builds but fails to start.
# ---------------------------------------------------------------------------
hiddenimports = []

# KM engine packages (reached only via the uvicorn string target)
for _km_pkg in (
    "api", "agent", "kg", "routing", "monitor", "extraction", "connectors",
    "proactive", "memory", "config", "tools", "guardrails", "eval", "simchat",
    "hermes_tools",
):
    hiddenimports += collect_submodules(_km_pkg)

# Web stack + ML libs with dynamic / lazy submodules
for _dep_pkg in (
    "uvicorn", "fastapi", "starlette",
    "langchain", "langgraph", "langchain_groq", "langchain_ollama",
    "langchain_community", "spacy", "networkx", "sentence_transformers",
    "chromadb",
):
    hiddenimports += collect_submodules(_dep_pkg)

hiddenimports += [
    # stdlib PyInstaller sometimes drops
    "sqlite3", "json", "pathlib", "threading", "webbrowser", "asyncio",
    "urllib.request", "urllib.error", "email.mime.text",
    # uvicorn picks these by name at runtime
    "anyio", "h11", "uvicorn.lifespan.on", "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto",
    # libraries imported lazily / inside functions
    "groq", "ollama", "tavily", "duckduckgo_search", "pypdf", "hnswlib",
    "slack_sdk",
    "google.auth", "google.oauth2.credentials",
    "google_auth_oauthlib.flow", "googleapiclient.discovery",
    # Hermes signal connectors (dispatched lazily by name)
    "connectors.strava", "connectors.spotify",
    "connectors.todoist", "connectors.apple_health",
]

a = Analysis(
    ["launcher.py"],
    pathex=[str(Path(".").resolve())],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # torch IS required by sentence-transformers (embeddings) -- do NOT exclude it.
        # scipy / sklearn / PIL are runtime deps of sentence-transformers -- keep them.
        "torchvision",  # text embeddings only
        "torchaudio",
        "tensorflow",
        "matplotlib",   # not used
        "cv2",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KnowledgeMind",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,           # server app: keep the console so logs/errors are visible
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="assets/icon.ico",   # uncomment and add an icon file
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="KnowledgeMind",
)
