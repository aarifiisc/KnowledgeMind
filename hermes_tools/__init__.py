"""
hermes_tools/
-------------
Signal derivation tools for the Hermes Agent extension.

Each module wraps one external connector, derives local signals, and
exposes a clean function that mcp_serve.py registers as an MCP tool.
All four tools are pinned LOCAL (privacy floor >= 0.90) — raw personal
data never reaches a cloud model.
"""
