---
sut_path: /home/exedev/llm-fuzzing
commit: uncommitted
updated: 2026-11-23
external_references:
  - path: https://antithesis.com/docs/configuration/the_antithesis_environment.md
    why: hardware limits of the Antithesis VM
---

# Deployment topology

One service, `llm-fuzz-agent` (image `llm-fuzz-agent:latest`, built from
`antithesis/Dockerfile` target `agent`).

```
llm-fuzz-agent
├── tini (init: true)
│   └── python -m harness.supervisor          entrypoint; emits setup_complete
│       └── llama-server 127.0.0.1:8080       1 thread, ctx 4096, 1 slot, --jinja
├── /models/model.gguf                        baked in, checksum-pinned
├── /workspace/…  /workspace/secret/secret.txt
├── /opt/agent/harness/…                      agent harness (PYTHONPATH)
├── /opt/antithesis/test/v1/<template>/…      one test template (build arg TEST_TEMPLATE)
└── /var/lib/token-fuzz/… or /var/lib/llm-fuzz/…   workload state
```

Why a single container: the user asked for model + harness + secret in one container,
and there is no cross-service behaviour to test. Network faults therefore do not touch
the localhost hop; CPU throttling and container pauses are the faults that matter, and
they only slow inference down.

## Startup

`setup_complete` is sent by the supervisor (SDK `lifecycle.setup_complete`) once
llama-server's `/health` returns `ok`. The compose healthcheck polls the same endpoint
for local `docker compose up --wait`.

## Test template `token_fuzz` (default, experiment 2)

| Command | Role |
|---|---|
| `first_configure_search.py` | draws the per-timeline search config (mode, vocab, prompt length, edit size), clears the search state |
| `serial_driver_search.py` | 4–16 candidate prompts per invocation: edit, probe the tool-call log-probability, run promising ones as real agent turns |
| `eventually_server_answers.py` | after faults stop, llama-server must be healthy and answer |

Only one template is installed per image so all of a run's timelines go to one
experiment; `TEST_TEMPLATE=llm_fuzz` switches back to experiment 1.

## Test template `llm_fuzz` (experiment 1)

| Command | Role |
|---|---|
| `first_configure_timeline.py` | draws the per-timeline swarm config, clears conversation state |
| `serial_driver_chat.py` | 1–3 random user turns per invocation, continuing or restarting the conversation |
| `eventually_server_answers.py` | after faults stop, llama-server must be healthy and answer |

`serial_driver_` rather than `parallel_driver_`: llama-server runs one slot on one core,
so concurrent conversations would only queue behind each other.

## Assumptions

- 10 GB is ample: model ~0.7 GB on tmpfs + KV cache < 0.5 GB + Python (llama-server RSS
  measured at ~1.2 GB). The host-RAM prompt cache (`--cache-ram`, default 8 GiB) is disabled.

## Open Questions

- Whether to raise `--parallel` and fuzz cross-slot KV-cache isolation (a different
  experiment: one conversation leaking into another).
