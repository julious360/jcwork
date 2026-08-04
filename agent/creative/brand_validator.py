"""Two-stage brand validation.

## Why two stages

Asking a vision model whether an image is 1080px wide, or whether a colour is within
tolerance of #2E5BFF, is slow, costs money, and gives a probabilistic answer to a
question with an exact one. Asking code whether the composition feels on-brand is
hopeless.

So the work is split by what each is actually good at:

* **Stage 1 (deterministic)** — real pixels and file metadata. Dimensions, aspect
  ratio, file size, and palette conformance measured as CIE76 ΔE in Lab space.
  Cheap, exact, and it runs first so an off-brand image is rejected before a single
  token is spent on it.
* **Stage 2 (vision model)** — tone, logo placement and safe area, composition, and
  forbidden claims. Judgement calls that have no closed form.

Stage 1 failures short-circuit: if the palette is wrong, the model is never called.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent.config import BrandGuide
from agent.creative.models import ValidationIssue, ValidationResult
from agent.llm import LLMClient, extract_json
from agent.logging_setup import get_logger

log = get_logger(__name__)

VISION_SYSTEM = """You are a meticulous brand design reviewer. You judge only what \
requires human-like visual judgement: tone, composition, logo treatment, and claim \
language. Dimensions and colour values have already been verified programmatically — \
do not comment on them.

Be strict but fair. Flag an issue only if you can point to what is wrong."""

VISION_PROMPT = """Review this advertisement against the brand guide.

TONE THE BRAND REQUIRES:
{tone}

LOGO RULES:
{logo_rules}

CLAIMS THAT MUST NOT APPEAR (in any wording):
{forbidden}

Return JSON exactly in this shape:
{{
  "passed": true,
  "issues": [
    {{"check": "tone|logo|composition|claims", "severity": "error|warning",
      "detail": "what specifically is wrong and where"}}
  ]
}}

Use severity "error" only for problems that should block publication."""


# ── Colour maths ──────────────────────────────────────────────────────────────


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    cleaned = value.lstrip("#")
    if len(cleaned) != 6:
        raise ValueError(f"expected a 6-digit hex colour, got {value!r}")
    return (int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16))


def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """sRGB to CIE L*a*b* (D65).

    Lab is used rather than RGB because euclidean distance in RGB does not track
    perceived difference — two colours the eye reads as identical can sit far apart
    in RGB, and vice versa.
    """

    def to_linear(channel: float) -> float:
        c = channel / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (to_linear(float(c)) for c in rgb)

    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = (r * 0.2126 + g * 0.7152 + b * 0.0722) / 1.00000
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t) + (16 / 116)

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    """CIE76 colour difference. ~2.3 is a just-noticeable difference."""
    return sum((a - b) ** 2 for a, b in zip(lab1, lab2, strict=True)) ** 0.5


# ── Stage 1: deterministic ────────────────────────────────────────────────────


def check_deterministic(image_path: Path, guide: BrandGuide) -> ValidationResult:
    from PIL import Image

    issues: list[ValidationIssue] = []

    size_mb = image_path.stat().st_size / (1024 * 1024)
    if size_mb > guide.max_file_size_mb:
        issues.append(
            ValidationIssue(
                check="file_size",
                severity="error",
                detail=f"{size_mb:.1f}MB exceeds the {guide.max_file_size_mb}MB limit",
            )
        )

    with Image.open(image_path) as image:
        rgb_image = image.convert("RGB")
        width, height = rgb_image.size

        if width < guide.min_width:
            issues.append(
                ValidationIssue(
                    check="dimensions",
                    severity="error",
                    detail=f"width {width}px is below the {guide.min_width}px minimum",
                )
            )

        ratio = width / height if height else 0.0
        if not any(
            abs(ratio - allowed) <= guide.aspect_ratio_tolerance
            for allowed in guide.allowed_aspect_ratios
        ):
            issues.append(
                ValidationIssue(
                    check="aspect_ratio",
                    severity="error",
                    detail=(
                        f"aspect ratio {ratio:.3f} is not one of {guide.allowed_aspect_ratios}"
                    ),
                )
            )

        coverage = _palette_coverage(rgb_image, guide)

    if coverage < guide.min_palette_coverage_pct:
        issues.append(
            ValidationIssue(
                check="palette",
                severity="error",
                detail=(
                    f"only {coverage:.1f}% of pixels are within ΔE {guide.max_delta_e} "
                    f"of the brand palette (minimum {guide.min_palette_coverage_pct}%)"
                ),
            )
        )

    return ValidationResult(
        passed=not any(i.severity == "error" for i in issues),
        issues=issues,
        palette_coverage_pct=round(coverage, 2),
        checked_by=["deterministic"],
    )


def _palette_coverage(image: object, guide: BrandGuide) -> float:
    """Share of pixels within ΔE tolerance of any brand colour.

    Downsampled to a small thumbnail first: at 128x128 the colour distribution is
    preserved while the ΔE comparison stays fast enough to run on every candidate.
    """
    from PIL import Image as PILImage

    assert isinstance(image, PILImage.Image)
    thumb = image.copy()
    thumb.thumbnail((128, 128))

    palette_lab = [rgb_to_lab(hex_to_rgb(color.hex)) for color in guide.palette]
    if not palette_lab:
        return 100.0

    pixels = list(thumb.getdata())
    if not pixels:
        return 0.0

    # Cache by quantised colour: photographic images repeat colours heavily, so this
    # collapses most of the per-pixel Lab conversions.
    cache: dict[tuple[int, int, int], bool] = {}
    on_palette = 0
    for pixel in pixels:
        key = (pixel[0] // 8 * 8, pixel[1] // 8 * 8, pixel[2] // 8 * 8)
        hit = cache.get(key)
        if hit is None:
            lab = rgb_to_lab(key)
            hit = any(delta_e(lab, target) <= guide.max_delta_e for target in palette_lab)
            cache[key] = hit
        if hit:
            on_palette += 1

    return 100.0 * on_palette / len(pixels)


# ── Stage 2: vision model ─────────────────────────────────────────────────────


def check_with_vision(image_path: Path, guide: BrandGuide, llm: LLMClient) -> ValidationResult:
    prompt = VISION_PROMPT.format(
        tone=guide.tone or "(none specified)",
        logo_rules=guide.logo_rules or "(none specified)",
        forbidden=", ".join(guide.forbidden_claims) or "(none)",
    )
    try:
        raw = llm.describe_image(image_path, prompt, system=VISION_SYSTEM)
        parsed = extract_json(raw)
    except Exception as exc:
        # A vision outage must not silently pass unreviewed creative, nor hard-fail
        # the pipeline. Flag for human review instead.
        log.warning("creative.vision_check_failed", error=str(exc))
        return ValidationResult(
            passed=False,
            issues=[
                ValidationIssue(
                    check="vision_unavailable",
                    severity="error",
                    detail=f"vision review could not be completed: {exc}",
                )
            ],
            checked_by=["vision"],
        )

    issues = [
        ValidationIssue(
            check=str(item.get("check", "vision")),
            severity=str(item.get("severity", "warning")),
            detail=str(item.get("detail", "")),
        )
        for item in parsed.get("issues", [])
    ]
    return ValidationResult(
        passed=bool(parsed.get("passed", False)) and not any(i.severity == "error" for i in issues),
        issues=issues,
        checked_by=["vision"],
    )


def validate_creative(
    image_path: Path, guide: BrandGuide, llm: LLMClient | None = None
) -> ValidationResult:
    """Run both stages, cheapest first."""
    deterministic = check_deterministic(image_path, guide)
    if not deterministic.passed:
        log.info(
            "creative.rejected_deterministically",
            path=str(image_path),
            reason=deterministic.summary(),
        )
        return deterministic  # never pay for a vision call on an image already failing

    if llm is None:
        return deterministic

    vision = check_with_vision(image_path, guide, llm)
    return ValidationResult(
        passed=deterministic.passed and vision.passed,
        issues=deterministic.issues + vision.issues,
        palette_coverage_pct=deterministic.palette_coverage_pct,
        checked_by=["deterministic", "vision"],
    )


def issues_as_feedback(result: ValidationResult) -> str:
    """Turn failures into a correction prompt for the next generation attempt."""
    return json.dumps([{"check": i.check, "problem": i.detail} for i in result.errors], indent=2)
