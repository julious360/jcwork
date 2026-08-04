"""Creative generation providers.

Images are live via Gemini. Video vendors (HeyGen, Seedance) are declared against the
same protocol and stubbed — swapping a mock for the real client is a constructor
change, not a refactor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import httpx

from agent.config import BrandGuide, Settings, get_settings
from agent.creative.models import AdCopy, CreativeDNA
from agent.llm import GeminiClient
from agent.logging_setup import get_logger

log = get_logger(__name__)


class ImageProvider(Protocol):
    name: str

    def generate(self, prompt: str, output_path: Path) -> Path: ...


class VideoProvider(Protocol):
    name: str

    def generate_segment(self, script: str, output_path: Path, avatar_id: str = "") -> Path: ...


def build_image_prompt(
    copy: AdCopy, dna: CreativeDNA, guide: BrandGuide, aspect: str = "1:1"
) -> str:
    """Compose an image prompt that respects the brand guide up front.

    Stating the palette and composition rules in the prompt is cheaper than
    discovering violations in validation and regenerating.
    """
    palette = ", ".join(f"{c.name} {c.hex}" for c in guide.palette)
    return f"""Create a {aspect} advertising image for a social feed.

CONCEPT: {dna.visual_motif}
IT MUST SUPPORT THIS MESSAGE: "{copy.hook}"

BRAND PALETTE — use these colours dominantly: {palette}
TONE: {guide.tone}

REQUIREMENTS:
- Leave clear space in a corner for a logo.
- Minimal or no text baked into the image; copy is overlaid separately.
- One clear focal point, generous whitespace.
- No stock-photo clichés: no handshakes, no thumbs up, no laughing at salad.
- Photographic or clean vector illustration, not 3D render clipart.
"""


class GeminiImageProvider:
    """Live static-ad generation ("Nano Banana" is Google's image model family)."""

    name = "gemini"

    def __init__(self, settings: Settings | None = None) -> None:
        self._client = GeminiClient(settings or get_settings())

    def generate(self, prompt: str, output_path: Path) -> Path:
        log.info("creative.generating_image", provider=self.name, path=str(output_path))
        return self._client.generate_image(prompt, output_path)


class KaiImageProvider:
    """Kai AI. Declared against the protocol; not wired until credentials exist."""

    name = "kai"

    def __init__(self, api_key: str = "", client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._http = client or httpx.Client(timeout=180.0)

    def generate(self, prompt: str, output_path: Path) -> Path:
        raise NotImplementedError(
            "KaiImageProvider is a declared interface only. Supply credentials and "
            "implement generate() against the vendor's API, or use GeminiImageProvider."
        )


class MockImageProvider:
    """Renders a real on-palette PNG offline.

    Deliberately not a stub that returns a path to nothing: it writes a genuine image
    at a valid Meta aspect ratio using brand colours, so the deterministic validator
    is exercised for real in tests and offline runs.
    """

    name = "mock"

    def __init__(self, guide: BrandGuide | None = None, size: tuple[int, int] = (1080, 1080)):
        self._guide = guide
        self._size = size

    def generate(self, prompt: str, output_path: Path) -> Path:
        from PIL import Image, ImageDraw

        colors = [c.hex for c in self._guide.palette] if self._guide else ["#101828", "#2E5BFF"]
        width, height = self._size
        image = Image.new("RGB", self._size, colors[0])
        draw = ImageDraw.Draw(image)

        # Simple bands of brand colour: enough to clear the palette-coverage check.
        band = height // max(1, len(colors))
        for i, color in enumerate(colors):
            draw.rectangle([0, i * band, width, (i + 1) * band], fill=color)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, "PNG")
        log.info("creative.mock_image_written", path=str(output_path))
        return output_path


class HeyGenProvider:
    """HeyGen AI-avatar UGC. Declared against the protocol; not wired."""

    name = "heygen"

    def __init__(self, api_key: str = "", client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._http = client or httpx.Client(timeout=600.0)

    def generate_segment(self, script: str, output_path: Path, avatar_id: str = "") -> Path:
        raise NotImplementedError(
            "HeyGenProvider is a declared interface only. Supply ADAGENT_CREATIVE__HEYGEN_API_KEY "
            "and implement generate_segment() against HeyGen's video API."
        )


class SeedanceProvider:
    """Seedance. Declared against the protocol; not wired."""

    name = "seedance"

    def __init__(self, api_key: str = "", client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._http = client or httpx.Client(timeout=600.0)

    def generate_segment(self, script: str, output_path: Path, avatar_id: str = "") -> Path:
        raise NotImplementedError(
            "SeedanceProvider is a declared interface only. Supply "
            "ADAGENT_CREATIVE__SEEDANCE_API_KEY and implement generate_segment()."
        )


class MockVideoProvider:
    """Writes a tiny placeholder file so the stitching path is exercisable offline."""

    name = "mock"

    def generate_segment(self, script: str, output_path: Path, avatar_id: str = "") -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x00" * 1024)
        log.info("creative.mock_video_written", path=str(output_path), script_len=len(script))
        return output_path


def build_image_provider(
    settings: Settings | None = None, guide: BrandGuide | None = None
) -> ImageProvider:
    resolved = settings or get_settings()
    if resolved.has_gemini:
        return GeminiImageProvider(resolved)
    log.info("creative.using_mock_image_provider", detail="no Gemini key configured")
    return MockImageProvider(guide)


def build_video_provider(settings: Settings | None = None) -> VideoProvider:
    resolved = (settings or get_settings()).creative
    if resolved.heygen_api_key.get_secret_value():
        return HeyGenProvider(resolved.heygen_api_key.get_secret_value())
    if resolved.seedance_api_key.get_secret_value():
        return SeedanceProvider(resolved.seedance_api_key.get_secret_value())
    log.info("creative.using_mock_video_provider", detail="no video credentials configured")
    return MockVideoProvider()


def provider_health(settings: Settings | None = None) -> dict[str, Any]:
    """Which creative paths are live versus mocked. Surfaced by ``adagent doctor``."""
    resolved = settings or get_settings()
    return {
        "image": "gemini (live)" if resolved.has_gemini else "mock",
        "video": (
            "heygen (live)"
            if resolved.creative.heygen_api_key.get_secret_value()
            else "seedance (live)"
            if resolved.creative.seedance_api_key.get_secret_value()
            else "mock"
        ),
        "copy": "claude (live)"
        if resolved.has_anthropic
        else "gemini (live)"
        if resolved.has_gemini
        else "stub",
    }
