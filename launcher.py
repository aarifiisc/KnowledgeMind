"""
launcher.py
-----------
Single entry point for KnowledgeMind.

Starts the FastAPI web app (api.main:app) with uvicorn and opens the browser.
The app seeds the knowledge graph on startup and exposes the Dashboard, Knowledge
Graph, Assistant, Documents, and Settings views. Configuration (model + keys) is
done in-app via the Settings view, so there is no separate setup step.

Run:
  python launcher.py
Then open http://127.0.0.1:8000
"""

from __future__ import annotations

import sys
import threading
import time
import webbrowser
from pathlib import Path

# Ensure repo root is on sys.path regardless of how the script is invoked.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

HOST = "127.0.0.1"
PORT = 8000


def _open_browser_when_ready(url: str, max_wait: int = 20) -> None:
    """Poll until the server responds, then open the browser."""
    import urllib.request

    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            webbrowser.open(url)
            return
        except Exception:
            time.sleep(0.4)
    webbrowser.open(url)  # fallback: open anyway


def main() -> None:
    # ASCII-only banner (Unicode box-drawing crashes on non-UTF8 consoles).
    print(r"""
   _  __                    _          _          __  __ _           _
  | |/ /_ __   _____      _| | ___  __| | __ _  __|  \/  (_)_ __   __| |
  | ' /| '_ \ / _ \ \ /\ / / |/ _ \/ _` |/ _` |/ _ \ |\/| | | '_ \ / _` |
  | . \| | | | (_) \ V  V /| |  __/ (_| | (_| |  __/ |  | | | | | | (_| |
  |_|\_\_| |_|\___/ \_/\_/ |_|\___|\__,_|\__, |\___|_|  |_|_|_| |_|\__,_|
                                         |___/

  Privacy-Aware Personal AI Agent  -  IISc Bengaluru
    """)

    url = f"http://{HOST}:{PORT}"
    threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()
    print(f"[Launcher] Starting KnowledgeMind at {url}")
    print("[Launcher] Configure your model/keys in the Settings view.")

    import uvicorn
    uvicorn.run("api.main:app", host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
