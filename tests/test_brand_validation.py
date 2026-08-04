"""Brand validation, both stages.

The load-bearing test here is that an off-palette image is rejected *before* the
vision model is consulted. Getting that ordering wrong means paying a model to tell
you what a histogram already knew.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from agent.config import BrandGuide
from agent.creative.brand_validator import (
    check_deterministic,
    delta_e,
    hex_to_rgb,
    rgb_to_lab,
    validate_creative,
)
from agent.creative.providers import MockImageProvider
from agent.llm import StubLLM


def test_hex_to_rgb() -> None:
    assert hex_to_rgb("#2E5BFF") == (46, 91, 255)
    assert hex_to_rgb("2E5BFF") == (46, 91, 255)


def test_delta_e_is_zero_for_identical_colours() -> None:
    lab = rgb_to_lab(hex_to_rgb("#2E5BFF"))
    assert delta_e(lab, lab) == 0.0


def test_delta_e_separates_perceptually_distant_colours() -> None:
    blue = rgb_to_lab(hex_to_rgb("#2E5BFF"))
    orange = rgb_to_lab(hex_to_rgb("#FFB020"))
    near_blue = rgb_to_lab(hex_to_rgb("#3060FF"))
    assert delta_e(blue, orange) > 100
    assert delta_e(blue, near_blue) < 12  # within the default tolerance


def test_on_brand_image_passes_deterministic_checks(
    brand_guide: BrandGuide, artifacts_dir: Path
) -> None:
    path = MockImageProvider(brand_guide).generate("prompt", artifacts_dir / "ok.png")
    result = check_deterministic(path, brand_guide)
    assert result.passed
    assert result.palette_coverage_pct > brand_guide.min_palette_coverage_pct


def test_off_palette_image_is_rejected(brand_guide: BrandGuide, artifacts_dir: Path) -> None:
    path = artifacts_dir / "off_palette.png"
    Image.new("RGB", (1080, 1080), "#00FF00").save(path)

    result = check_deterministic(path, brand_guide)
    assert not result.passed
    assert any(issue.check == "palette" for issue in result.errors)


def test_wrong_dimensions_are_rejected(brand_guide: BrandGuide, artifacts_dir: Path) -> None:
    path = artifacts_dir / "small.png"
    Image.new("RGB", (500, 500), brand_guide.palette[0].hex).save(path)

    result = check_deterministic(path, brand_guide)
    assert not result.passed
    assert any(issue.check == "dimensions" for issue in result.errors)


def test_wrong_aspect_ratio_is_rejected(brand_guide: BrandGuide, artifacts_dir: Path) -> None:
    path = artifacts_dir / "wide.png"
    Image.new("RGB", (1920, 1080), brand_guide.palette[0].hex).save(path)

    result = check_deterministic(path, brand_guide)
    assert not result.passed
    assert any(issue.check == "aspect_ratio" for issue in result.errors)


def test_deterministic_failure_short_circuits_the_vision_model(
    brand_guide: BrandGuide, artifacts_dir: Path
) -> None:
    """No tokens are spent on an image the pixel checks already rejected."""
    calls: list[str] = []

    class RecordingLLM(StubLLM):
        def describe_image(self, image_path: Path, prompt: str, *, system: str = "") -> str:
            calls.append(str(image_path))
            return '{"passed": true, "issues": []}'

    path = artifacts_dir / "bad.png"
    Image.new("RGB", (400, 400), "#00FF00").save(path)

    result = validate_creative(path, brand_guide, RecordingLLM())
    assert not result.passed
    assert calls == []
    assert result.checked_by == ["deterministic"]


def test_vision_stage_runs_when_deterministic_passes(
    brand_guide: BrandGuide, artifacts_dir: Path
) -> None:
    path = MockImageProvider(brand_guide).generate("prompt", artifacts_dir / "ok.png")
    result = validate_creative(path, brand_guide, StubLLM())
    assert result.checked_by == ["deterministic", "vision"]
    assert result.passed


def test_vision_errors_route_to_review_rather_than_passing(
    brand_guide: BrandGuide, artifacts_dir: Path
) -> None:
    """A vision outage must not become a silent approval."""

    class BrokenLLM(StubLLM):
        def describe_image(self, image_path: Path, prompt: str, *, system: str = "") -> str:
            raise RuntimeError("vision provider unavailable")

    path = MockImageProvider(brand_guide).generate("prompt", artifacts_dir / "ok.png")
    result = validate_creative(path, brand_guide, BrokenLLM())
    assert not result.passed
    assert any(issue.check == "vision_unavailable" for issue in result.errors)


def test_vision_reported_error_fails_validation(
    brand_guide: BrandGuide, artifacts_dir: Path
) -> None:
    llm = StubLLM(
        {
            "vision": '{"passed": false, "issues": [{"check": "claims", '
            '"severity": "error", "detail": "uses the word guaranteed"}]}'
        }
    )
    path = MockImageProvider(brand_guide).generate("prompt", artifacts_dir / "ok.png")
    result = validate_creative(path, brand_guide, llm)
    assert not result.passed
    assert result.errors[0].check == "claims"
