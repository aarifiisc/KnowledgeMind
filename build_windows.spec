# build_windows.spec
# ------------------
# PyInstaller spec for building KnowledgeMind.exe on Windows.
#
# Usage:
#   pip install pyinstaller
#   pyinstaller build_windows.spec
#
# Output: dist/KnowledgeMind/KnowledgeMind.exe  (folder bundle)
#         dist/KnowledgeMind.exe                 (single file — slower startup)
#
# Run with --onedir for faster startup, --onefile for single portable exe.
# Recommended: --onedir (bundled in a folder)

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect data files from packages that use them at runtime
datas = []
datas += collect_data_files("gradio")
datas += collect_data_files("gradio_client")
datas += collect_data_files("spacy")
datas += collect_data_files("en_core_web_sm")   # spaCy English model
datas += collect_data_files("pyvis")

# Include our own data directory (mock data, etc.)
datas += [("data", "data")]

# Hidden imports that PyInstaller misses via static analysis
hiddenimports = []
hiddenimports += collect_submodules("gradio")
hiddenimports += collect_submodules("langchain")
hiddenimports += collect_submodules("langgraph")
hiddenimports += collect_submodules("langchain_groq")
hiddenimports += collect_submodules("langchain_community")
hiddenimports += collect_submodules("spacy")
hiddenimports += collect_submodules("networkx")
hiddenimports += collect_submodules("sentence_transformers")
hiddenimports += [
    "sqlite3",
    "json",
    "pathlib",
    "threading",
    "webbrowser",
    "urllib.request",
    "urllib.error",
    "groq",
    "tavily",
    "duckduckgo_search",
    "slack_sdk",
    "google.auth",
    "google.oauth2.credentials",
    "google_auth_oauthlib.flow",
    "googleapiclient.discovery",
    "pyvis.network",
    "ollama",
]

a = Analysis(
    ["launcher.py"],
    pathex=[str(Path(".").resolve())],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # torch is REQUIRED by sentence-transformers (embeddings) — do NOT exclude it.
        # Likewise scipy / sklearn / PIL are runtime deps of sentence-transformers.
        "torchvision",  # not needed — text embeddings only
        "torchaudio",
        "tensorflow",
        "matplotlib",   # not used
        "cv2",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KnowledgeMind",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # No console window — UI-only app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="assets/icon.ico",   # uncomment and add icon file
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="KnowledgeMind",
)
