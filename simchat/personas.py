"""
simchat/personas.py
-------------------
LLM-backed persona agents for the SimChat application.

Three distinct virtual personalities that respond to Alex's messages:
  BOB   — terse, one-sentence replies, no filler
  ANNIE — formal, complete sentences, professional tone
  CINDY — casual, slang-heavy, enthusiastic

Each persona receives only its own conversation history as context (per-spec
isolation). The Groq cloud model is used for persona responses — simulated
dialogue contains no personal data so cloud routing applies. Falls back to a
deterministic mock string when GROQ_API_KEY is not set, so smoke tests and
offline demos run without a live LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config.store import get_config


# Each history entry mirrors Gradio's Chatbot format: (user_text, persona_text).
# persona_text is None when the response is still pending.
HistoryEntry = tuple[str, Optional[str]]


@dataclass
class Persona:
    """A virtual conversation partner with a fixed communication style."""

    name: str
    system_prompt: str

    def respond(
        self,
        history: list[HistoryEntry],
        user_message: str,
        current_date: str = "",
    ) -> str:
        """
        Generate a reply as this persona.

        Args:
            history:      The thread's message history as (user, persona) pairs.
                          Only this persona's thread is passed — isolation is
                          enforced by the caller (simchat/app.py).
            user_message: Alex's latest message.
            current_date: Simulated CURRENT_DATE string ('YYYY-MM-DD').
        Returns:
            The persona's reply text (never empty; falls back to mock offline).
        """
        cfg = get_config()
        if not cfg.groq_api_key:
            return self._mock_response(user_message)

        try:
            from groq import Groq

            date_note = f" Today's simulated date is {current_date}." if current_date else ""
            system = self.system_prompt + date_note

            messages: list[dict] = [{"role": "system", "content": system}]
            for user_turn, persona_turn in history:
                messages.append({"role": "user", "content": user_turn})
                if persona_turn is not None:
                    messages.append({"role": "assistant", "content": persona_turn})
            messages.append({"role": "user", "content": user_message})

            client = Groq(api_key=cfg.groq_api_key)
            response = client.chat.completions.create(
                model=cfg.cloud_model_fast,
                messages=messages,
                temperature=0.8,
                max_tokens=200,
            )
            return response.choices[0].message.content.strip()

        except Exception as err:  # noqa: BLE001 — degrade gracefully
            print(f"[Persona:{self.name}] WARNING: Groq call failed ({err}); using mock.")
            return self._mock_response(user_message)

    def _mock_response(self, user_message: str) -> str:
        """Tone-consistent offline placeholder (no LLM required)."""
        if self.name == "Bob":
            return "Works for me."
        if self.name == "Annie":
            return (
                "Thank you for your message. I have noted the proposed time "
                "and will confirm my availability shortly."
            )
        # Cindy
        return "omg yes!! haha just lmk the deets and I'm there!!"


# ---------------------------------------------------------------------------
# Singleton persona instances
# ---------------------------------------------------------------------------

BOB = Persona(
    name="Bob",
    system_prompt=(
        "You are Bob, a colleague of the person you are chatting with. "
        "Reply in one short sentence — direct, no filler, no greeting. "
        "Under 15 words. Confirm or counter-propose times plainly."
    ),
)

ANNIE = Persona(
    name="Annie",
    system_prompt=(
        "You are Annie, a formal professional contact of the person you are chatting with. "
        "Always write in complete, grammatically correct sentences with proper punctuation. "
        "Be polite and structured; avoid slang or abbreviations. "
        "When scheduling, confirm dates clearly or suggest a formal alternative. "
        "Reply in 1–3 complete sentences only."
    ),
)

CINDY = Persona(
    name="Cindy",
    system_prompt=(
        "You are Cindy, a casual friend of the person you are chatting with. "
        "Text like a friend — short, contractions, informal, light slang "
        "('omg', 'haha', 'ngl', 'tbh', 'sounds lit'). "
        "Enthusiastic and relaxed about scheduling. Max 2 short sentences."
    ),
)

PERSONAS: dict[str, Persona] = {
    "bob": BOB,
    "annie": ANNIE,
    "cindy": CINDY,
}


# ---------------------------------------------------------------------------
# Smoke test (no LLM required)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from unittest.mock import patch
    from config.store import AppConfig

    # _mock_response returns non-empty for every persona.
    for persona in PERSONAS.values():
        reply = persona._mock_response("Let's grab coffee tomorrow at 3pm.")
        assert reply, f"{persona.name} mock reply is empty"
        print(f"=> {persona.name} mock: {reply!r}")

    # respond() falls through to mock when groq_api_key is unset.
    stub_cfg = AppConfig(groq_api_key="")
    with patch("simchat.personas.get_config", return_value=stub_cfg):
        for persona in PERSONAS.values():
            result = persona.respond([], "Coffee at 10am tomorrow?", "2026-06-24")
            assert result, f"{persona.name}.respond() returned empty in mock mode"
            print(f"=> {persona.name}.respond() offline: {result!r}")

    # History is passed correctly — test that history list is consumed without error.
    history: list[HistoryEntry] = [
        ("Are you free Friday?", "Works for me."),
        ("Great — 3pm?", None),
    ]
    stub_cfg2 = AppConfig(groq_api_key="")
    with patch("simchat.personas.get_config", return_value=stub_cfg2):
        r = BOB.respond(history, "Perfect, see you then.", "2026-06-27")
        assert r, "respond() with history should not return empty"
        print(f"=> BOB.respond() with history: {r!r}")

    print("All simchat/personas.py smoke tests passed.")
