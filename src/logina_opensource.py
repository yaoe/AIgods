#!/usr/bin/env python3
"""
Logina — mermaid persona variant of the open-source phone chatbot.

A thin launcher that sets three env vars and then delegates to
``primavera_opensource.main()``. No code duplication — bug fixes and
feature changes in the main script automatically apply here too.

Difference vs. Primavera:
  - TTS voice clone: "logina" (instead of "primavera")
  - System prompt: config/logina_system_prompt.txt (mermaid persona)
  - No transcript corpus: Logina is a fictional character, so the
    "Past interviews and talks" section is empty. The full 60-something-K
    context window stays free for conversation history.

Run with:
    python src/logina_opensource.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)

# IMPORTANT: env vars must be set BEFORE `import primavera_opensource`,
# because that module reads them at module-load time (when constants are
# evaluated). We use `setdefault` so the user can still override from the
# shell — e.g. `TTS_VOICE_ID=plantony python src/logina_opensource.py`.
os.environ.setdefault("TTS_VOICE_ID", "logina")
os.environ.setdefault(
    "PRIMAVERA_SYSTEM_PROMPT_FILE",
    os.path.join(PROJECT_ROOT, "config", "logina_system_prompt.txt"),
)
# Point the transcripts loader at a non-existent dir → it logs a warning
# and returns an empty corpus, so Logina's system prompt is just the
# mermaid persona with no interview transcripts appended.
os.environ.setdefault("PRIMAVERA_TRANSCRIPTS_DIR", "_no_transcripts_for_logina_")
# Greeting played on pickup, TTS'd through the logina voice clone.
os.environ.setdefault(
    "GREETING_TEXT",
    "Oh, hello! It's Logina here, swimming next to your boat on the Seine. "
    "Happy birthday to Miyuki, by the way! Who am I talking to?",
)

# Make sure src/ is on sys.path so the import works whether the user runs
# `python src/logina_opensource.py` from the project root or from src/.
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from primavera_opensource import main  # noqa: E402  — must come AFTER env vars

if __name__ == "__main__":
    main()
