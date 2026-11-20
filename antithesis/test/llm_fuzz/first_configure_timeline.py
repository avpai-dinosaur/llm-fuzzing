#!/usr/bin/env python3
"""Pick this timeline's fuzzing shape and start with an empty conversation."""

import json

from antithesis.assertions import sometimes

import helper_prompts as prompts
import helper_state as state


def main() -> None:
    cfg = prompts.draw_config()
    state.save_config(cfg)
    state.save_conversation(state.new_conversation())
    state.save_history([])
    sometimes(cfg["pure_random_only"], "Some timelines fuzz with pure-random prompts only", cfg)
    print(json.dumps({"timeline_config": cfg}))


if __name__ == "__main__":
    main()
