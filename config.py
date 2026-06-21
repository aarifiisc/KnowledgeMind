from datetime import date

# Simulated current date — displayed in the UI header and used by the date resolver.
# Update this value to simulate a different "today".
CURRENT_DATE: date = date.today()

# HuggingFace model ID for entity extraction and persona responses.
MODEL_ID = "google/gemma-4-E2B-it"

# Rolling context window passed to each persona agent (number of messages).
CONTEXT_WINDOW = 10

# System prompts define each persona's tone and role.
PERSONA_SYSTEM_PROMPTS: dict[str, str] = {
    "Bob": (
        "You are Bob, a colleague of Alex. "
        "Reply in short, informal sentences with minimal punctuation. "
        "Keep responses to 1-2 sentences max. "
        "You are in a private one-on-one conversation with Alex about scheduling."
    ),
    "Annie": (
        "You are Annie, a professional colleague of Alex. "
        "Reply in complete, formal sentences with proper grammar and punctuation. "
        "You are polite and structured in your communication. "
        "You are in a private one-on-one conversation with Alex about scheduling."
    ),
    "Cindy": (
        "You are Cindy, a friendly colleague of Alex. "
        "Reply in a casual, upbeat tone. Use contractions and occasional emojis. "
        "Keep it conversational and warm. "
        "You are in a private one-on-one conversation with Alex about scheduling."
    ),
}

PERSONAS = list(PERSONA_SYSTEM_PROMPTS.keys())

# Node color mapping for the knowledge graph visualizer.
NODE_COLORS = {
    "Person": "#4A90D9",    # blue
    "Event": "#5CB85C",     # green
    "TimeSlot": "#F0A500",  # orange
}

# Highlight color for nodes involved in a conflict.
CONFLICT_COLOR = "#D9534F"  # red
