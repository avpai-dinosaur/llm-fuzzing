#!/usr/bin/env python3
"""Pick this timeline's search shape and start with no prompt."""

import json

import helper_search as search


def main() -> None:
    cfg = search.draw_config()
    search.save_config(cfg)
    search.save_search(search.new_search())
    print(json.dumps({"timeline_config": cfg}))


if __name__ == "__main__":
    main()
