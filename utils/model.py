from __future__ import annotations

import streamlit as st
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline as hf_pipeline

from config import MODEL_ID


@st.cache_resource(show_spinner="Loading language model…")
def load_pipe():
    """
    Load the Gemma model once and cache it for the entire Streamlit session.
    Both persona_agent and extraction_agent share this single instance.
    Generation parameters (temperature, max_new_tokens, etc.) are passed at
    call time so each agent can use its own settings.
    """
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        device_map="auto",
        torch_dtype="auto",
    )
    pipe = hf_pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        return_full_text=False,
    )
    return pipe, tokenizer
