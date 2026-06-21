from __future__ import annotations

import json
import re

from pydantic import ValidationError

from graph.graph_store import apply_entities
from utils.date_resolver import resolve_date, resolve_time
from utils.model import load_pipe
from utils.schema import EventEntity

# Number of recent messages passed to the extractor as context.
_EXTRACTION_CONTEXT = 4

_FEW_SHOT_PROMPT = """\
You are a scheduling event extractor. Given a conversation between Alex and {persona}, \
extract all scheduling commitments and output them as a JSON array.

Each item must have exactly these fields:
- "person": always "{persona}"
- "activity": short label for the event (e.g. "coffee", "lunch", "meeting", "sync")
- "date_str": the date exactly as mentioned in the conversation \
(e.g. "Friday", "tomorrow", "next Monday", "June 20")
- "time_str": time in HH:MM 24-hour format (e.g. "15:00", "13:00"). \
Use "TBD" if no time is mentioned.
- "action": "add" for new plans, "remove" for cancellations. \
For rescheduling, emit two items: one "remove" (old slot) and one "add" (new slot).

Rules:
- Output ONLY a valid JSON array. No explanation, no markdown, no extra text.
- If there is no scheduling commitment, output [].

Examples:

Conversation (Alex → Bob):
Alex: Hey Bob, want to grab lunch this Friday at noon?
Bob: Sure, sounds great!
Output: [{{"person": "Bob", "activity": "lunch", "date_str": "this Friday", "time_str": "12:00", "action": "add"}}]

Conversation (Alex → Annie):
Alex: Annie, let's cancel our Thursday meeting.
Annie: Understood. I will clear my calendar.
Output: [{{"person": "Annie", "activity": "meeting", "date_str": "Thursday", "time_str": "TBD", "action": "remove"}}]

Conversation (Alex → Bob):
Alex: Bob, can we move our Tuesday sync to Wednesday at 3 PM?
Bob: Works for me.
Output: [{{"person": "Bob", "activity": "sync", "date_str": "Tuesday", "time_str": "TBD", "action": "remove"}}, \
{{"person": "Bob", "activity": "sync", "date_str": "Wednesday", "time_str": "15:00", "action": "add"}}]

Conversation (Alex → Cindy):
Alex: Hey Cindy, how's it going?
Cindy: All good!
Output: []

Now extract from this conversation:
{conversation}
Output:"""


def _build_prompt(persona: str, messages: list[dict]) -> str:
    lines = [f"{m['role']}: {m['content']}" for m in messages[-_EXTRACTION_CONTEXT:]]
    return _FEW_SHOT_PROMPT.format(
        persona=persona,
        conversation="\n".join(lines),
    )


def _parse_entities(raw: str, persona: str) -> list[EventEntity]:
    """Extract and validate a JSON array from potentially noisy LLM output."""
    # Find the first '[' … last ']' block in the output
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []

    try:
        items = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        # Try stripping trailing commas and retry
        cleaned = re.sub(r",\s*([}\]])", r"\1", raw[start : end + 1])
        try:
            items = json.loads(cleaned)
        except json.JSONDecodeError:
            return []

    entities: list[EventEntity] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # Ensure the person field is always the active persona
        item["person"] = persona
        # Resolve natural-language date and time to normalised forms
        item["date_str"] = resolve_date(item.get("date_str", ""))
        item["time_str"] = resolve_time(item.get("time_str", "TBD"))
        try:
            entities.append(EventEntity(**item))
        except ValidationError:
            continue  # silently drop malformed entries

    return entities


def extract(persona: str, messages: list[dict]) -> list[EventEntity]:
    """
    Extract scheduling entities from the latest exchange in a DM conversation.

    Args:
        persona: The persona Alex is talking to in this conversation thread.
        messages: The full conversation history (only the last
                  _EXTRACTION_CONTEXT messages are used).

    Returns:
        List of validated EventEntity objects with resolved dates and times.
        Side effect: calls graph_store.apply_entities() to update the graph.
    """
    pipe, _ = load_pipe()
    prompt = _build_prompt(persona, messages)

    try:
        output = pipe(prompt, max_new_tokens=512, do_sample=False)
        raw = output[0]["generated_text"]
    except Exception:  # noqa: BLE001
        return []

    entities = _parse_entities(raw, persona)
    if entities:
        apply_entities(entities)

    return entities
