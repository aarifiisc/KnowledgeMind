"""
ui/setup.py
-----------
First-launch setup screen shown when config is missing or incomplete.
Collects: local model selection, Groq API key, Tavily API key (optional),
          Slack token (optional).

After saving, reloads into the main UI (ui/app.py).
"""

from __future__ import annotations

import sys
import time
import threading
from pathlib import Path

import gradio as gr

from config.store import get_config, save_config, reload_config, AppConfig
from config.models import list_ollama_models, get_recommended_models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_groq_key(api_key: str) -> tuple[bool, str]:
    """Test Groq API key with a minimal call. Returns (valid, message)."""
    if not api_key or not api_key.startswith("gsk_"):
        return False, "Key must start with 'gsk_'"
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5,
        )
        return True, "✓ Groq API key is valid"
    except Exception as e:
        err = str(e)
        if "401" in err or "invalid" in err.lower():
            return False, "✗ Invalid API key — check at console.groq.com"
        return False, f"✗ Could not reach Groq: {err[:80]}"


def _get_model_choices() -> tuple[list[str], str]:
    """Return (choices_for_dropdown, status_message)."""
    cfg = get_config()
    models, error = list_ollama_models(cfg.ollama_base_url)
    recommended = get_recommended_models()

    if error:
        return [], error

    # Sort: recommended models first, rest alphabetically
    ordered = []
    for r in recommended:
        # Match by prefix (e.g. "qwen2.5:3b" matches "qwen2.5:3b")
        matches = [m for m in models if m == r or m.startswith(r.split(":")[0])]
        ordered.extend(matches)
    rest = [m for m in models if m not in ordered]
    ordered.extend(rest)

    # Remove duplicates preserving order
    seen = set()
    final = []
    for m in ordered:
        if m not in seen:
            seen.add(m)
            final.append(m)

    status = f"✓ Found {len(final)} model(s). Recommended: qwen2.5:3b"
    return final, status


# ---------------------------------------------------------------------------
# Setup UI builder
# ---------------------------------------------------------------------------

def build_setup_ui(on_complete_callback) -> gr.Blocks:
    """
    Build the setup Gradio Blocks interface.

    on_complete_callback: called with no args when setup is saved successfully.
    Used by launcher.py to switch to main UI.
    """
    cfg = get_config()
    initial_models, initial_model_status = _get_model_choices()
    initial_model_value = (
        cfg.local_model if cfg.local_model in initial_models
        else (initial_models[0] if initial_models else None)
    )

    with gr.Blocks(
        title="KnowledgeMind — Setup",
        theme=gr.themes.Soft(primary_hue="blue"),
        css="""
            .setup-header { text-align: center; padding: 20px 0 10px 0; }
            .section-card { border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; margin: 8px 0; }
            .required-label::after { content: ' *'; color: #e53935; }
            footer { display: none !important; }
        """,
    ) as setup_ui:

        gr.HTML("""
            <div class="setup-header">
                <h1 style="color:#1B3A6B; font-size:2.2em; margin:0">🧠 KnowledgeMind</h1>
                <p style="color:#555; margin:4px 0 0 0">Privacy-Aware Personal AI Agent — First Launch Setup</p>
                <p style="color:#888; font-size:0.9em">Your settings are stored locally. No data leaves your device.</p>
            </div>
        """)

        # ── Step 1: Local Model ─────────────────────────────────────────────
        with gr.Group(elem_classes=["section-card"]):
            gr.Markdown("### 1 · Local Model (runs on your device)")

            model_status = gr.Markdown(
                value=initial_model_status if initial_model_status else
                      "⚠ Ollama not detected. Start Ollama first, then click Refresh.",
                label=""
            )

            with gr.Row():
                model_dropdown = gr.Dropdown(
                    choices=initial_models,
                    value=initial_model_value,
                    label="Select local model",
                    info="Recommended: qwen2.5:3b (best tool-calling at 3B size)",
                    interactive=True,
                    scale=4,
                )
                refresh_btn = gr.Button("↻ Refresh", scale=1, variant="secondary")

            gr.Markdown(
                "*Don't see your model? Run `ollama pull qwen2.5:3b` in a terminal, then click Refresh.*",
                visible=True,
            )

        # ── Step 2: API Keys ────────────────────────────────────────────────
        with gr.Group(elem_classes=["section-card"]):
            gr.Markdown("### 2 · API Keys")

            groq_key = gr.Textbox(
                label="Groq API Key  (required)",
                placeholder="gsk_...",
                type="password",
                value=cfg.groq_api_key,
                info="Free at console.groq.com — gives access to Llama 3.3-70B for planning",
            )
            groq_status = gr.Markdown("")

            with gr.Row():
                validate_groq_btn = gr.Button("Test Groq Key", variant="secondary", scale=1)
                gr.HTML("<div style='flex:3'></div>")

            gr.HTML("<hr style='margin:12px 0; border-color:#eee'>")

            tavily_key = gr.Textbox(
                label="Tavily Search API Key  (optional)",
                placeholder="tvly-...",
                type="password",
                value=cfg.tavily_api_key,
                info="Free at tavily.com — better web search results. Falls back to DuckDuckGo if blank.",
            )

        # ── Step 3: Optional Connectors ─────────────────────────────────────
        with gr.Group(elem_classes=["section-card"]):
            gr.Markdown("### 3 · Connectors  *(optional — can be added later in Settings)*")

            slack_token = gr.Textbox(
                label="Slack Bot Token",
                placeholder="xoxb-...",
                type="password",
                value=cfg.slack_bot_token,
                info="From api.slack.com/apps — needed for Slack message monitoring",
            )

            google_creds_path = gr.Textbox(
                label="Google OAuth Credentials Path",
                placeholder="./credentials.json",
                value=cfg.google_credentials_path,
                info="Download from Google Cloud Console → APIs & Services → Credentials (OAuth 2.0 Desktop app)",
            )

            gr.Markdown(
                "*Without these, the system uses mock data for Slack and Calendar. "
                "Everything else works normally.*"
            )

        # ── Save button ─────────────────────────────────────────────────────
        with gr.Row():
            save_btn = gr.Button("💾  Save & Launch KnowledgeMind", variant="primary", scale=3)
            save_status = gr.Markdown("", scale=2)

        # ── Event handlers ──────────────────────────────────────────────────

        def on_refresh_models():
            models, status = _get_model_choices()
            if models:
                return (
                    gr.Dropdown(choices=models, value=models[0]),
                    gr.Markdown(status),
                )
            return (
                gr.Dropdown(choices=[], value=None),
                gr.Markdown(f"⚠ {status}"),
            )

        def on_validate_groq(key):
            if not key.strip():
                return gr.Markdown("Enter your Groq API key first.")
            valid, msg = _validate_groq_key(key.strip())
            colour = "#2e7d32" if valid else "#c62828"
            return gr.Markdown(f"<span style='color:{colour}'>{msg}</span>")

        def on_save(model, groq, tavily, slack, google_path):
            errors = []

            if not model:
                errors.append("Select a local model (or install one via Ollama).")
            if not groq.strip():
                errors.append("Groq API key is required.")

            if errors:
                return gr.Markdown(
                    "**Cannot save:**\n" + "\n".join(f"- {e}" for e in errors)
                )

            # Validate Groq key
            valid, msg = _validate_groq_key(groq.strip())
            if not valid:
                return gr.Markdown(f"**Groq key error:** {msg}")

            # Save config
            cfg = get_config()
            cfg.local_model = model
            cfg.groq_api_key = groq.strip()
            cfg.tavily_api_key = tavily.strip()
            cfg.slack_bot_token = slack.strip()
            cfg.google_credentials_path = google_path.strip()
            cfg.setup_complete = True
            save_config(cfg)
            reload_config()

            # Trigger main UI switch
            threading.Thread(target=_delayed_callback, args=(on_complete_callback,), daemon=True).start()

            return gr.Markdown("✓ Saved. Launching KnowledgeMind...")

        def _delayed_callback(fn):
            time.sleep(0.8)
            fn()

        refresh_btn.click(on_refresh_models, outputs=[model_dropdown, model_status])
        validate_groq_btn.click(on_validate_groq, inputs=groq_key, outputs=groq_status)
        save_btn.click(
            on_save,
            inputs=[model_dropdown, groq_key, tavily_key, slack_token, google_creds_path],
            outputs=save_status,
        )

    return setup_ui
