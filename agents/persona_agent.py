from __future__ import annotations

from config import PERSONA_SYSTEM_PROMPTS, CONTEXT_WINDOW
from utils.model import load_pipe


def _build_prompt(persona: str, messages: list[dict], current_message: str, tokenizer) -> str:
    """
    Format the conversation as a single-turn Gemma chat prompt.

    System context and rolling history are embedded in the user turn so
    the model receives full scheduling context without needing multi-turn
    formatting (which can confuse smaller Gemma variants).
    """
    system_text = (
        f"{PERSONA_SYSTEM_PROMPTS[persona]}\n\n"
        "You are in a private one-on-one conversation with Alex about scheduling. "
        "Reply ONLY as your character in 1-3 sentences. "
        "Do NOT prefix your reply with your own name."
    )

    # `messages` contains only prior turns — the current Alex message is
    # appended separately, so there is no duplication in the prompt.
    history_lines = [f"{m['role']}: {m['content']}" for m in messages[-CONTEXT_WINDOW:]]
    history_block = "\n".join(history_lines)

    if history_block:
        user_content = (
            f"{system_text}\n\n"
            f"Conversation so far:\n{history_block}\n\n"
            f"Alex: {current_message}"
        )
    else:
        user_content = f"{system_text}\n\nAlex: {current_message}"

    return tokenizer.apply_chat_template(
        [{"role": "user", "content": user_content}],
        tokenize=False,
        add_generation_prompt=True,
    )


def _clean_reply(raw: str, persona: str) -> str:
    """Strip any leading 'PersonaName: ' the model might hallucinate."""
    text = raw.strip()
    if text.lower().startswith(f"{persona.lower()}:"):
        text = text[len(persona) + 1:].strip()
    for token in ("<end_of_turn>", "<eos>", "<|end|>"):
        text = text.replace(token, "").strip()
    return text


def get_reply(
    persona: str,
    messages: list[dict],
    current_message: str,
) -> tuple[str, str]:
    """
    Generate a reply from the given persona to Alex's latest message.
    `messages` is the prior conversation history for this persona only
    (does NOT include the current_message yet).

    Returns:
        (persona_name, reply_text)
    """
    pipe, tokenizer = load_pipe()
    prompt = _build_prompt(persona, messages, current_message, tokenizer)

    try:
        output = pipe(
            prompt,
            max_new_tokens=256,
            do_sample=True,
            temperature=0.7,
            repetition_penalty=1.1,
        )
        reply = _clean_reply(output[0]["generated_text"], persona)
    except Exception as exc:  # noqa: BLE001
        reply = f"[Model error: {exc}]"

    return persona, reply
