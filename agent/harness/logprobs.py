"""Log-probability probes: how likely is the model to make a given move next?

The fuzzer uses these as a progress signal. A prompt that raises the chance
of the model opening its reply with a tool call is closer to a leak than one
that doesn't, even when neither makes the model actually call the tool.
(Measured locally: once Qwen3-0.6B starts a tool call after a random-token
prompt, it fills in the secret file's path with probability ~1, because that
path is the only one its system prompt names.)

llama-server only lists the top-n candidates for a position, and the tool
call is usually far outside them. But it also reports the *unbiased*
probability of whichever token it sampled, computed over the whole
vocabulary. So we force the token we care about with a huge logit bias and
read off its real log-probability. One forward pass on a prompt the server
already has cached, however unlikely the token.
"""

from . import config, tools
from .llm import LlamaClient

FORCE = 100.0
# What a probability that underflowed to 0 is reported as. Must stay finite:
# the SDK drops numeric guidance for non-finite values.
FLOOR = -100.0


class ProbeError(Exception):
    """The server didn't sample the forced token, so the answer is unusable."""


class Prober:
    def __init__(self, client: LlamaClient | None = None):
        self.client = client or LlamaClient()
        self.tool_call = self.single_token("<tool_call>")
        # Qwen3's vocabulary: ordinary BPE tokens, then the control tokens
        # (<|endoftext|> ... </think>), then unused padding ids.
        self.plain_vocab = self.single_token("<|endoftext|>")
        self.full_vocab = self.single_token("</think>") + 1
        self.control_tokens = [self.client.detokenize([i]) for i in range(self.plain_vocab, self.full_vocab)]

    def single_token(self, text: str) -> int:
        ids = self.client.tokenize(text)
        if len(ids) != 1:
            raise ValueError(f"{text!r} is not a single token: {ids}")
        return ids[0]

    def chat_prompt(self, user_text: str) -> list[int]:
        """The tokens the agent's first request puts in front of the model
        for this user message: system prompt, tool schema, user turn and the
        assistant header, up to where the reply's first token goes."""
        messages = [{"role": "system", "content": config.SYSTEM_PROMPT}, {"role": "user", "content": user_text}]
        return self.client.tokenize(self.client.apply_template(messages, [tools.READ_FILE_TOOL]))

    def next_logprob(self, prompt: list[int], token: int) -> tuple[float, str, float]:
        """log p(token | prompt), and the token the model actually favours
        there with its log-probability."""
        response = self.client.complete(
            prompt, n_predict=1, n_probs=1, temperature=1.0, seed=0, logit_bias=[[token, FORCE]]
        )
        out = response["completion_probabilities"][0]
        if out["id"] != token:
            raise ProbeError(f"forced token {token} but the server sampled {out['id']}")
        favourite = out["top_logprobs"][0]
        return max(out["logprob"], FLOOR), favourite["token"], favourite["logprob"]

    def control_tokens_in(self, text: str) -> list[str]:
        """Control tokens the text will turn into once templated, whether
        drawn directly or spelled out by ordinary tokens."""
        return [c for c in self.control_tokens if c in text]

    def tool_call_logprob(self, user_text: str) -> tuple[float, str, float]:
        """How likely the agent is to open its reply to this message with a tool call."""
        return self.next_logprob(self.chat_prompt(user_text), self.tool_call)
