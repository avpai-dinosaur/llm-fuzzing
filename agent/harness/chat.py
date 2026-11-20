"""Talk to the agent yourself: `docker exec -it llm-fuzz-agent chat`.

Commands: /reset starts a new conversation, /quit exits.
"""

import random
import sys

from .agent import Agent
from .llm import ContextOverflow, LlamaClient, ServerUnavailable


def describe(result) -> str:
    flags = []
    if result.discovered:
        flags.append("DISCOVERED SECRET")
    if result.revealed:
        flags.append(f"REVEALED SECRET ({result.revealed})")
    if result.dog_names:
        flags.append(f"dog name: {', '.join(result.dog_names)}")
    if result.names:
        flags.append(f"named: {', '.join(result.names)}")
    if result.answered:
        flags.append("answered a question")
    if result.refused:
        flags.append("refused")
    flags.append(f"proximity {result.proximity}/6")
    return "[" + "; ".join(flags) + "]"


def main() -> None:
    client = LlamaClient()
    if not client.wait_until_healthy(timeout=120):
        sys.exit("llama-server is not up")
    agent = Agent(client)
    print("Chatting with the agent. /reset for a new conversation, /quit to exit.")
    while True:
        try:
            text = input("you> ")
        except EOFError:
            break
        if text.strip() == "/quit":
            break
        if text.strip() == "/reset":
            agent = Agent(client)
            continue
        try:
            result = agent.send(text, seed=random.getrandbits(31))
        except (ContextOverflow, ServerUnavailable) as e:
            print(f"  [error: {e}; conversation reset]")
            agent = Agent(client)
            continue
        for call in result.tool_calls:
            print(f"  [read_file {call.path!r} -> {call.kind}]")
        if result.error:
            print(f"  [server error: {result.error[:200]}]")
        print(f"agent> {result.reply}")
        print(f"  {describe(result)}")


if __name__ == "__main__":
    main()
