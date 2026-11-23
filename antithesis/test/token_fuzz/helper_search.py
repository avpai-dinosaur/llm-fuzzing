"""Random-token prompts, and the search state that carries them from one
test command to the next.

A prompt is a list of token ids drawn uniformly from the model's own
vocabulary: no words, no templates, no knowledge of the task. Each driver
command proposes edits to the timeline's current prompt and scores every
candidate by how likely the agent is to open its reply with a tool call
(harness.logprobs).

Search modes, one per timeline (swarm testing):
  restart  every candidate is a fresh random prompt: the no-search baseline
  walk     always move to the edited prompt. Antithesis does the selecting:
           its guidance favours branching from states where the score was
           high, and each branch keeps editing from there
  climb    keep an edit only if it doesn't lower the score: a plain hill
           climb in the harness, for comparison with walk

Every random decision goes through the Antithesis SDK, so Antithesis can
replay any prompt and branch to try different ones.
"""

import json
import os
from pathlib import Path

from antithesis.random import get_random, random_choice

STATE_DIR = Path(os.environ.get("TOKEN_FUZZ_STATE_DIR", "/var/lib/token-fuzz"))
MAX_PROMPT_TOKENS = 64
EDITS = ("replace", "replace", "replace", "insert", "delete")


def below(n: int) -> int:
    return get_random() % n


def chance(p: float) -> bool:
    return below(1 << 20) < p * (1 << 20)


def draw_config() -> dict:
    return {
        "mode": random_choice(["restart", "walk", "walk", "climb", "climb"]),
        # "all" adds the 26 control tokens (<tool_call>, <|im_start|>, ...),
        # each about 1 in 150k draws; "plain" is ordinary text tokens only.
        "vocab": random_choice(["plain", "all"]),
        "prompt_tokens": random_choice([4, 8, 16, 32, 48]),
        "edits_per_candidate": random_choice([1, 1, 2, 4]),
        "candidates_per_command": random_choice([4, 8, 16]),
        # Besides every promising candidate, also run this share of the rest
        # as a real agent turn, to catch tool calls that come later in a reply.
        "full_turn_chance": random_choice([0.0, 0.05, 0.2]),
        "temperature": random_choice([0.0, 0.7]),
        "max_tokens": 128,
    }


def random_prompt(length: int, vocab_size: int) -> list[int]:
    return [below(vocab_size) for _ in range(length)]


def edit(tokens: list[int], vocab_size: int, n: int) -> tuple[list[int], list[str]]:
    out = list(tokens)
    done = []
    for _ in range(n):
        op = random_choice(EDITS)
        if op == "delete" and len(out) > 1:
            del out[below(len(out))]
        elif op == "insert" and len(out) < MAX_PROMPT_TOKENS:
            out.insert(below(len(out) + 1), below(vocab_size))
        else:
            op = "replace"
            out[below(len(out))] = below(vocab_size)
        done.append(op)
    return out, done


# Persistent state ------------------------------------------------------------


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
        cfg = draw_config()
        save_config(cfg)
    return cfg


def new_search() -> dict:
    """current: the prompt edits start from. best/initial: for reporting
    how far the timeline's search has come. Prompts are {"tokens", "score"}."""
    return {"current": None, "best": None, "initial": None, "evaluations": 0}


def load_search() -> dict:
    search = _read("search.json", None)
    return search if isinstance(search, dict) else new_search()


def save_search(search: dict) -> None:
    _write("search.json", search)
