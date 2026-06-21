"""
launcher.py
-----------
Single entry point for KnowledgeMind.
Works as:
  - python launcher.py          (development)
  - KnowledgeMind.exe           (Windows PyInstaller bundle)
  - ./knowledgemind.sh          (Linux shell launcher)

Launch flow:
  1. Check config — setup complete?
  2a. NO  → show setup UI (ui/setup.py)
  2b. YES → show main UI (ui/app.py)
  3. Open browser automatically
  4. Background monitor loop starts after main UI loads
"""

from __future__ import annotations

import os
import sys
import time
import threading
import webbrowser
from pathlib import Path

# Ensure repo root is on sys.path regardless of how the script is invoked
# (handles both `python launcher.py` and PyInstaller bundled execution)
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

PORT = 7860
HOST = "127.0.0.1"


# ---------------------------------------------------------------------------
# Browser opener (waits for server to be ready)
# ---------------------------------------------------------------------------

def _open_browser_when_ready(url: str, max_wait: int = 15):
    """Poll until server responds, then open browser."""
    import urllib.request
    import urllib.error

    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            webbrowser.open(url)
            return
        except Exception:
            time.sleep(0.4)
    # Fallback: just open anyway
    webbrowser.open(url)


# ---------------------------------------------------------------------------
# Main UI (after setup)
# ---------------------------------------------------------------------------

def launch_main_ui():
    """Build and launch the main Gradio UI, then start the monitor loop."""
    from ui.app import build_main_ui
    from config.store import get_config

    cfg = get_config()
    app = build_main_ui(cfg)

    # Start the proactive monitor FSM in its own daemon thread (SPEC 4.1).
    # start() returns immediately; the loop is fully guarded so a monitor
    # failure can never crash the UI process.
    from monitor.fsm import monitor_runner
    monitor_runner.start()
    print("[Launcher] Monitor FSM started in background.")

    threading.Thread(
        target=_open_browser_when_ready,
        args=(f"http://{HOST}:{PORT}",),
        daemon=True,
    ).start()

    app.launch(
        server_name=HOST,
        server_port=PORT,
        show_error=True,
        quiet=True,
        inbrowser=False,   # we handle browser opening ourselves
    )


# ---------------------------------------------------------------------------
# Setup UI (first launch)
# ---------------------------------------------------------------------------

def launch_setup_ui():
    """Show setup/onboarding screen. On completion, restart into main UI."""
    from ui.setup import build_setup_ui

    _setup_done = threading.Event()

    def on_setup_complete():
        _setup_done.set()

    setup_app = build_setup_ui(on_complete_callback=on_setup_complete)

    # Open browser for setup
    threading.Thread(
        target=_open_browser_when_ready,
        args=(f"http://{HOST}:{PORT}",),
        daemon=True,
    ).start()

    # Launch setup UI in a background thread so we can detect completion
    server_thread = threading.Thread(
        target=lambda: setup_app.launch(
            server_name=HOST,
            server_port=PORT,
            show_error=True,
            quiet=True,
            inbrowser=False,
            prevent_thread_lock=True,
        ),
        daemon=True,
    )
    server_thread.start()

    # Wait until setup is done
    _setup_done.wait()

    # Close setup server and restart as main UI
    # Gradio doesn't expose a clean shutdown — we use os.execv to restart
    print("[Launcher] Setup complete. Restarting into main UI...")
    time.sleep(1.0)

    # Restart the process cleanly
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    # ASCII-only banner: Unicode box-drawing / 'x' crash on non-UTF8 consoles
    # (Windows cp1252), which would abort launch before the UI starts.
    print(r"""
   _  __                    _          _          __  __ _           _
  | |/ /_ __   _____      _| | ___  __| | __ _  __|  \/  (_)_ __   __| |
  | ' /| '_ \ / _ \ \ /\ / / |/ _ \/ _` |/ _` |/ _ \ |\/| | | '_ \ / _` |
  | . \| | | | (_) \ V  V /| |  __/ (_| | (_| |  __/ |  | | | | | | (_| |
  |_|\_\_| |_|\___/ \_/\_/ |_|\___|\__,_|\__, |\___|_|  |_|_|_| |_|\__,_|
                                         |___/

  Privacy-Aware Personal AI Agent
  IISc Bengaluru
    """)

    from config.store import get_config
    cfg = get_config()

    if cfg.is_ready():
        print(f"[Launcher] Config found. Local model: {cfg.local_model}")
        print(f"[Launcher] Starting main UI at http://{HOST}:{PORT}")
        launch_main_ui()
    else:
        print("[Launcher] No config found. Starting setup UI...")
        launch_setup_ui()


if __name__ == "__main__":
    main()
