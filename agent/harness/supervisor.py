"""Container entrypoint: run llama-server, tell Antithesis when it is ready,
and restart it (flagging the crash) if it ever dies."""

import os
import shlex
import signal
import subprocess
import sys
import time

from antithesis.assertions import reachable, unreachable
from antithesis.lifecycle import setup_complete

from . import config
from .llm import LlamaClient


def llama_command() -> list[str]:
    return [
        "llama-server",
        "--model", config.MODEL_PATH,
        "--host", config.LLAMA_HOST,
        "--port", str(config.LLAMA_PORT),
        "--threads", str(config.LLAMA_THREADS),
        "--threads-batch", str(config.LLAMA_THREADS),
        "--ctx-size", str(config.CTX_SIZE),
        "--parallel", "1",
        # The host-RAM prompt cache defaults to 8 GiB; the whole Antithesis VM
        # has 10 GB. One slot already reuses the shared system-prompt prefix.
        "--cache-ram", "0",
        "--jinja",
        "--no-webui",
        "--log-colors", "off",
        *shlex.split(os.environ.get("LLAMA_EXTRA_ARGS", "")),
    ]


def wait_ready(proc: subprocess.Popen, client: LlamaClient) -> bool:
    while proc.poll() is None:
        if client.healthy():
            return True
        time.sleep(0.5)
    return False


def main() -> None:
    stopping = False
    proc = None

    def stop(signum, frame):
        nonlocal stopping
        stopping = True
        if proc and proc.poll() is None:
            proc.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    client = LlamaClient(timeout=10)
    announced = False
    while not stopping:
        print(f"supervisor: starting {shlex.join(llama_command())}", flush=True)
        proc = subprocess.Popen(llama_command())
        if wait_ready(proc, client) and not announced:
            reachable("Inference server started and passed its health check", {"model": config.MODEL_PATH})
            setup_complete({"model": config.MODEL_PATH, "ctx_size": config.CTX_SIZE})
            print("supervisor: llama-server is healthy, setup complete", flush=True)
            announced = True
        returncode = proc.wait()
        if stopping:
            break
        print(f"supervisor: llama-server exited with {returncode}, restarting", flush=True)
        unreachable("llama-server exited unexpectedly", {"returncode": returncode})
        time.sleep(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
