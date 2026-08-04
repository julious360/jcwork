"""LLM access: text, vision, and embeddings, behind one small interface.

Claude and Gemini are both wired live. Everything downstream depends on this module
rather than on a vendor SDK, so swapping providers — or running the whole pipeline
offline against ``StubLLM`` — touches one file.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from pathlib import Path
from typing import Any, Protocol

from agent.config import Settings, get_settings
from agent.logging_setup import get_logger

log = get_logger(__name__)


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 4096) -> str: ...

    def complete_json(
        self, prompt: str, *, system: str = "", max_tokens: int = 4096
    ) -> dict[str, Any]: ...

    def describe_image(self, image_path: Path, prompt: str, *, system: str = "") -> str: ...

    def embed(self, text: str) -> list[float]: ...


def extract_json(text: str) -> dict[str, Any]:
    """Pull a JSON object out of a model response.

    Models wrap JSON in prose or fences more often than not; failing the whole
    pipeline over a stray `````json`` fence would be needlessly brittle.
    """
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None

    if candidate is None:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError(f"no JSON object found in response: {text[:200]}")
        candidate = text[start : end + 1]

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMError(f"malformed JSON in response: {exc}") from exc

    if not isinstance(parsed, dict):
        raise LLMError("expected a JSON object at the top level")
    return parsed


class AnthropicClient:
    """Claude. Used for copy, pain-point clustering, and vision judgement."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: Any = None

    def _ensure(self) -> Any:
        if self._client is None:
            import anthropic

            key = self._settings.llm.anthropic_api_key.get_secret_value()
            if not key:
                raise LLMError("ADAGENT_LLM__ANTHROPIC_API_KEY is not set")
            self._client = anthropic.Anthropic(
                api_key=key, timeout=self._settings.llm.request_timeout_seconds
            )
        return self._client

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 4096) -> str:
        response = self._ensure().messages.create(
            model=self._settings.llm.text_model,
            max_tokens=max_tokens,
            system=system or "You are a precise assistant. Answer exactly what is asked.",
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    def complete_json(
        self, prompt: str, *, system: str = "", max_tokens: int = 4096
    ) -> dict[str, Any]:
        instruction = (
            f"{system}\n\nRespond with a single JSON object and nothing else."
            if system
            else "Respond with a single JSON object and nothing else."
        )
        return extract_json(self.complete(prompt, system=instruction, max_tokens=max_tokens))

    def describe_image(self, image_path: Path, prompt: str, *, system: str = "") -> str:
        import base64

        media_type = _media_type(image_path)
        encoded = base64.standard_b64encode(image_path.read_bytes()).decode()
        response = self._ensure().messages.create(
            model=self._settings.llm.vision_model,
            max_tokens=self._settings.llm.max_tokens,
            system=system or "You are a meticulous brand design reviewer.",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": encoded,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    def embed(self, text: str) -> list[float]:
        # Anthropic exposes no embeddings endpoint; novelty scoring uses the
        # deterministic local embedder instead. See HashingEmbedder.
        return HashingEmbedder().embed(text)


class GeminiClient:
    """Gemini. Primary image generator; also usable for text and vision."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: Any = None

    def _ensure(self) -> Any:
        if self._client is None:
            from google import genai

            key = self._settings.llm.gemini_api_key.get_secret_value()
            if not key:
                raise LLMError("ADAGENT_LLM__GEMINI_API_KEY is not set")
            self._client = genai.Client(api_key=key)
        return self._client

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 4096) -> str:
        full = f"{system}\n\n{prompt}" if system else prompt
        response = self._ensure().models.generate_content(model="gemini-2.5-flash", contents=full)
        return str(response.text or "")

    def complete_json(
        self, prompt: str, *, system: str = "", max_tokens: int = 4096
    ) -> dict[str, Any]:
        return extract_json(
            self.complete(
                prompt,
                system=f"{system}\n\nRespond with a single JSON object and nothing else.",
                max_tokens=max_tokens,
            )
        )

    def describe_image(self, image_path: Path, prompt: str, *, system: str = "") -> str:
        from google.genai import types

        part = types.Part.from_bytes(
            data=image_path.read_bytes(), mime_type=_media_type(image_path)
        )
        response = self._ensure().models.generate_content(
            model="gemini-2.5-flash", contents=[part, f"{system}\n\n{prompt}".strip()]
        )
        return str(response.text or "")

    def generate_image(self, prompt: str, output_path: Path) -> Path:
        """Generate a static ad image and write it to ``output_path``."""
        response = self._ensure().models.generate_content(
            model=self._settings.llm.image_model, contents=prompt
        )
        for candidate in response.candidates or []:
            for part in candidate.content.parts or []:
                inline = getattr(part, "inline_data", None)
                if inline and inline.data:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(inline.data)
                    return output_path
        raise LLMError("Gemini returned no image data")

    def embed(self, text: str) -> list[float]:
        try:
            response = self._ensure().models.embed_content(
                model="text-embedding-004", contents=text
            )
            return list(response.embeddings[0].values)
        except Exception as exc:
            log.warning("llm.embed_fallback", error=str(exc))
            return HashingEmbedder().embed(text)


class HashingEmbedder:
    """Deterministic offline embedder.

    A hashed token-trigram bag: no network, no API key, stable across runs. It is a
    weaker semantic signal than a real embedding model, but it reliably catches the
    thing the novelty gate is actually for — the agent re-shipping a near-copy of a
    concept it already ran.
    """

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        vector = [0.0] * self.dimensions
        grams = tokens + [" ".join(tokens[i : i + 2]) for i in range(max(0, len(tokens) - 1))]
        for gram in grams:
            digest = hashlib.blake2b(gram.encode(), digest_size=8).digest()
            index = struct.unpack("<Q", digest)[0] % self.dimensions
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class StubLLM:
    """Offline stand-in so the full pipeline runs with no keys and no network."""

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self._responses = responses or {}
        self._embedder = HashingEmbedder()

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 4096) -> str:
        return str(self._responses.get("text", "stub response"))

    def complete_json(
        self, prompt: str, *, system: str = "", max_tokens: int = 4096
    ) -> dict[str, Any]:
        return dict(self._responses.get("json", {}))

    def describe_image(self, image_path: Path, prompt: str, *, system: str = "") -> str:
        return str(self._responses.get("vision", '{"passed": true, "issues": []}'))

    def embed(self, text: str) -> list[float]:
        return self._embedder.embed(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def build_llm(settings: Settings | None = None) -> LLMClient:
    """Pick the best available text/vision client, falling back to the stub."""
    resolved = settings or get_settings()
    if resolved.has_anthropic:
        return AnthropicClient(resolved)
    if resolved.has_gemini:
        return GeminiClient(resolved)
    log.warning("llm.no_keys_configured", detail="falling back to StubLLM")
    return StubLLM()


def _media_type(path: Path) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(path.suffix.lower(), "image/png")
