"""State that outlives a single test command: the timeline's fuzzing config,
the ongoing conversation, and recent prompts (seeds for mutation).

A conversation is {"messages": [...], "strategies": [...], "turns_since_discovery": int | None}.
"""

import json
import os
from pathlib import Path

import helper_prompts as prompts

STATE_DIR = Path(os.environ.get("LLM_FUZZ_STATE_DIR", "/var/lib/llm-fuzz"))
HISTORY_LENGTH = 10


def _read(name: str, default):
    try:
        return json.loads((STATE_DIR / name).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(name: str, value) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_DIR / (name + ".tmp")
    tmp.write_text(json.dumps(value))
    tmp.replace(STATE_DIR / name)


def save_config(cfg: dict) -> None:
    _write("config.json", cfg)


def load_config() -> dict:
    cfg = _read("config.json", None)
    if cfg is None:  # first_ did not run (e.g. a local invocation)
        cfg = prompts.draw_config()
        save_config(cfg)
    return cfg


def new_conversation() -> dict:
    return {"messages": None, "strategies": [], "turns_since_discovery": None}


def load_conversation() -> dict:
    conversation = _read("conversation.json", None)
    return conversation if isinstance(conversation, dict) else new_conversation()


def save_conversation(conversation: dict) -> None:
    _write("conversation.json", conversation)


def load_history() -> list[str]:
    return _read("history.json", [])


def save_history(history: list[str]) -> None:
    _write("history.json", history[-HISTORY_LENGTH:])
