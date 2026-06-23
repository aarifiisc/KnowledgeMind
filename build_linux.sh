#!/usr/bin/env bash
# build_linux.sh
# --------------
# Linux launcher for KnowledgeMind.
# Creates a venv, installs deps, downloads spaCy model, and starts the app.
#
# Usage:
#   chmod +x build_linux.sh
#   ./build_linux.sh          # first run: installs everything
#   ./build_linux.sh --run    # subsequent runs: skip install, just launch
#
# The app opens automatically in your default browser at http://127.0.0.1:8000

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON="python3"
PIP="$VENV_DIR/bin/pip"
PYTHON_VENV="$VENV_DIR/bin/python"

# ── Colours ─────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${BLUE}[KnowledgeMind]${NC} $1"; }
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }

# ── Banner ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}  ██╗  ██╗███╗   ██╗ ██████╗ ██╗    ██╗██╗     ███████╗██████╗  ██████╗ ███████╗"
echo -e "  ██╔╝██╔╝████╗  ██║██╔═══██╗██║    ██║██║     ██╔════╝██╔══██╗██╔════╝ ██╔════╝"
echo -e "  █████╔╝ ██╔██╗ ██║██║   ██║██║ █╗ ██║██║     █████╗  ██║  ██║██║  ███╗█████╗  "
echo -e "  ██╔═██╗ ██║╚██╗██║██║   ██║██║███╗██║██║     ██╔══╝  ██║  ██║██║   ██║██╔══╝  "
echo -e "  ██║  ██╗██║ ╚████║╚██████╔╝╚███╔███╔╝███████╗███████╗██████╔╝╚██████╔╝███████╗"
echo -e "  ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝  ╚══╝╚══╝ ╚══════╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝${NC}"
echo ""
echo "  Privacy-Aware Personal AI Agent"
echo "  IISc Bengaluru"
echo ""

# ── Run-only mode ─────────────────────────────────────────────────────────
if [[ "$1" == "--run" ]]; then
    if [[ ! -f "$PYTHON_VENV" ]]; then
        fail "Virtual environment not found. Run without --run first to install."
    fi
    log "Starting KnowledgeMind..."
    exec "$PYTHON_VENV" "$SCRIPT_DIR/launcher.py"
fi

# ── Python check ──────────────────────────────────────────────────────────
log "Checking Python version..."
if ! command -v "$PYTHON" &>/dev/null; then
    fail "python3 not found. Install Python 3.11+ and try again."
fi

PYTHON_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$("$PYTHON" -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$("$PYTHON" -c "import sys; print(sys.version_info.minor)")

if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 11 ]]; then
    fail "Python 3.11+ required. Found: $PYTHON_VERSION"
fi
ok "Python $PYTHON_VERSION"

# ── Ollama check ──────────────────────────────────────────────────────────
log "Checking Ollama..."
if command -v ollama &>/dev/null; then
    ok "Ollama found: $(ollama --version 2>/dev/null | head -1)"
else
    warn "Ollama not found. Install from https://ollama.com/download"
    warn "You can still set up API keys, but local model won't work until Ollama is installed."
fi

# ── Virtual environment ───────────────────────────────────────────────────
if [[ ! -d "$VENV_DIR" ]]; then
    log "Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
    ok "Virtual environment created at $VENV_DIR"
else
    ok "Virtual environment exists"
fi

# ── Install dependencies ──────────────────────────────────────────────────
log "Installing dependencies (this may take a few minutes on first run)..."
"$PIP" install --upgrade pip --quiet
"$PIP" install -r "$SCRIPT_DIR/requirements.txt" --quiet
ok "Dependencies installed"

# ── spaCy model ───────────────────────────────────────────────────────────
log "Checking spaCy model..."
if "$PYTHON_VENV" -c "import en_core_web_sm" 2>/dev/null; then
    ok "spaCy model en_core_web_sm already installed"
else
    log "Downloading spaCy English model (~12 MB)..."
    "$PYTHON_VENV" -m spacy download en_core_web_sm --quiet
    ok "spaCy model installed"
fi

# ── Data directory ────────────────────────────────────────────────────────
if [[ ! -d "$SCRIPT_DIR/data" ]]; then
    mkdir -p "$SCRIPT_DIR/data"
    log "Created data/ directory"
fi

# ── Front-end build (React SPA served by FastAPI) ──────────────────────────
# FastAPI serves frontend/dist; build it once with Node if it is missing.
if [[ ! -d "$SCRIPT_DIR/frontend/dist" ]]; then
    if command -v npm &>/dev/null; then
        log "Building front-end (first run, may take a minute)..."
        ( cd "$SCRIPT_DIR/frontend" && npm install && npm run build )
        ok "Front-end built"
    else
        warn "npm not found and frontend/dist missing - the web UI will not load."
        warn "Install Node.js 20+ from https://nodejs.org, then re-run."
    fi
fi

# ── Create desktop shortcut (optional) ────────────────────────────────────
DESKTOP_FILE="$HOME/.local/share/applications/knowledgemind.desktop"
if [[ ! -f "$DESKTOP_FILE" ]] && [[ -d "$HOME/.local/share/applications" ]]; then
    cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=KnowledgeMind
Comment=Privacy-Aware Personal AI Agent
Exec=bash $SCRIPT_DIR/build_linux.sh --run
Icon=$SCRIPT_DIR/assets/icon.png
Terminal=false
Categories=Utility;AI;
StartupNotify=true
EOF
    ok "Desktop shortcut created"
fi

# ── Launch ────────────────────────────────────────────────────────────────
echo ""
log "Starting KnowledgeMind at http://127.0.0.1:8000 ..."
echo ""
exec "$PYTHON_VENV" "$SCRIPT_DIR/launcher.py"
