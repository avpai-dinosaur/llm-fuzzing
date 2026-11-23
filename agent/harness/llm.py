"""Tiny stdlib client for llama-server's OpenAI-compatible API."""

import http.client
import json
import os
import time
import urllib.error
import urllib.request

from . import config


class LlamaError(Exception):
    """Base class for inference-server failures."""


class ServerUnavailable(LlamaError):
    """The server could not be reached: starting, restarting, or too slow."""


class ContextOverflow(LlamaError):
    """The conversation no longer fits in the model's context window."""


class ServerError(LlamaError):
    """The server answered with an error status."""

    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


def _extra_params() -> dict:
    # e.g. LLAMA_EXTRA_PARAMS='{"chat_template_kwargs": {"enable_thinking": false}}'
    raw = os.environ.get("LLAMA_EXTRA_PARAMS", "")
    return json.loads(raw) if raw else {}


class LlamaClient:
    def __init__(self, base_url: str = config.LLAMA_URL, timeout: float = 900):
        self.base_url = base_url
        # Generous: Antithesis may throttle the CPU mid-request.
        self.timeout = timeout
        self.extra = _extra_params()

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", "replace")
            except (OSError, http.client.HTTPException):
                body = ""
            if "exceed_context_size" in body:
                raise ContextOverflow(body) from e
            if e.code == 503:
                raise ServerUnavailable(body) from e
            raise ServerError(e.code, body) from e
        # Refused/reset connections, timeouts, truncated or garbled responses:
        # all mean the server is (re)starting, overloaded or was paused.
        except (OSError, http.client.HTTPException, ValueError) as e:
            raise ServerUnavailable(f"{type(e).__name__}: {e}") from e

    def healthy(self) -> bool:
        try:
            return self._request("GET", "/health").get("status") == "ok"
        except LlamaError:
            return False

    def wait_until_healthy(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.healthy():
                return True
            time.sleep(1)
        return False

    def chat(self, messages: list, tools: list, *, temperature: float, seed: int, max_tokens: int) -> dict:
        payload = {
            "messages": messages,
            "temperature": temperature,
            "seed": seed,
            "max_tokens": max_tokens,
            "cache_prompt": True,
            **self.extra,
        }
        if tools:
            payload["tools"] = tools
        return self._request("POST", "/v1/chat/completions", payload)

    # Lower-level endpoints, for the log-probability probes.

    def model_meta(self) -> dict:
        return self._request("GET", "/v1/models")["data"][0]["meta"]

    def tokenize(self, text: str) -> list[int]:
        # parse_special: "<tool_call>" in the text becomes the control token,
        # as it does when a chat request is templated.
        return self._request("POST", "/tokenize", {"content": text, "parse_special": True})["tokens"]

    def detokenize(self, ids: list[int]) -> str:
        return self._request("POST", "/detokenize", {"tokens": ids})["content"]

    def apply_template(self, messages: list, tools: list) -> str:
        """The prompt text a chat request with these messages would produce."""
        payload = {"messages": messages, **self.extra}
        if tools:
            payload["tools"] = tools
        return self._request("POST", "/apply-template", payload)["prompt"]

    def complete(self, prompt: list[int], **params) -> dict:
        """Raw completion from token ids, no chat template or tool parsing."""
        return self._request("POST", "/completion", {"prompt": prompt, "cache_prompt": True, **params})
