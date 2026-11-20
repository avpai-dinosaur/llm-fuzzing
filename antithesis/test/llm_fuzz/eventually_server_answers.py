#!/usr/bin/env python3
"""Once faults stop, the inference server must be up and able to answer.
Catches prompts that crash or wedge llama-server for good."""

from antithesis.assertions import always

from harness.llm import LlamaClient, LlamaError


def main() -> None:
    client = LlamaClient(timeout=600)
    healthy = client.wait_until_healthy(timeout=600)
    answered, error = False, ""
    if healthy:
        try:
            response = client.chat([{"role": "user", "content": "Say OK."}], [], temperature=0.0, seed=1, max_tokens=4)
            answered = bool(response.get("choices"))
        except LlamaError as e:
            error = str(e)[:500]
    always(healthy and answered, "Inference server answers requests once faults stop", {"healthy": healthy, "error": error})


if __name__ == "__main__":
    main()
