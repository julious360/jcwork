"""The creative pipeline end to end, offline.

Proves the generate -> validate -> regenerate loop terminates: it produces a
validated asset when it can, retries with the specific failures fed back when it
cannot, and hands the asset to a human rather than looping forever or shipping
something unchecked.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from agent.config import BrandGuide, CampaignConfig, Settings
from agent.creative.models import AdCopy, CreativeDNA
from agent.creative.pipeline import CreativePipeline, build_video_script
from agent.creative.providers import MockImageProvider, build_image_prompt
from agent.creative.stitcher import FFmpegUnavailableError, VideoStitcher
from agent.llm import StubLLM
from agent.research.models import PainPoint

COPY_JSON = {
    "hook": "Two hours a day answering 'where are we on this?'",
    "primary_text": "Status chasing eats the morning. Then the real work starts at noon.",
    "headline": "Stop chasing status",
    "description": "See it all in one place",
    "cta": "LEARN_MORE",
}


@pytest.fixture
def pain_point() -> PainPoint:
    return PainPoint(
        id="status_chasing",
        problem="Clients constantly ask for status updates",
        desired_outcome="Clients can see status without asking",
        frequency=0.6,
        emotional_intensity=0.8,
        commercial_intent=0.7,
        supporting_quotes=["I spend the first two hours of every day on this"],
    )


@pytest.fixture
def settings(artifacts_dir: Path) -> Settings:
    resolved = Settings()
    resolved.creative.artifact_dir = artifacts_dir
    resolved.creative.max_validation_attempts = 3
    return resolved


def _llm(**overrides: object) -> StubLLM:
    return StubLLM({"json": COPY_JSON, "vision": '{"passed": true, "issues": []}', **overrides})


def test_pipeline_produces_a_validated_asset(
    pain_point: PainPoint, campaign: CampaignConfig, brand_guide: BrandGuide, settings: Settings
) -> None:
    pipeline = CreativePipeline(_llm(), MockImageProvider(brand_guide), brand_guide, settings)
    asset = pipeline.generate_static(pain_point, campaign, "problem_agitation", "a clean chart")

    assert asset.status == "validated"
    assert asset.local_path is not None and asset.local_path.exists()
    assert asset.validation is not None and asset.validation.passed
    assert asset.ad_copy.headline == "Stop chasing status"
    assert asset.dna.pain_point_id == "status_chasing"


def test_unfixable_creative_is_routed_to_human_review(
    pain_point: PainPoint, campaign: CampaignConfig, brand_guide: BrandGuide, settings: Settings
) -> None:
    """After max attempts the asset is parked, not shipped and not silently dropped."""

    class OffBrandProvider:
        name = "off_brand"

        def __init__(self) -> None:
            self.attempts = 0

        def generate(self, prompt: str, output_path: Path) -> Path:
            self.attempts += 1
            output_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (1080, 1080), "#00FF00").save(output_path)
            return output_path

    provider = OffBrandProvider()
    pipeline = CreativePipeline(_llm(), provider, brand_guide, settings)
    asset = pipeline.generate_static(pain_point, campaign, "before_after", "a green square")

    assert asset.status == "needs_review"
    assert provider.attempts == settings.creative.max_validation_attempts
    assert asset.validation is not None and not asset.validation.passed


def test_generation_errors_do_not_crash_the_pipeline(
    pain_point: PainPoint, campaign: CampaignConfig, brand_guide: BrandGuide, settings: Settings
) -> None:
    class BrokenProvider:
        name = "broken"

        def generate(self, prompt: str, output_path: Path) -> Path:
            raise RuntimeError("image provider exploded")

    pipeline = CreativePipeline(_llm(), BrokenProvider(), brand_guide, settings)
    asset = pipeline.generate_static(pain_point, campaign, "contrarian_take", "motif")

    assert asset.status == "needs_review"
    assert asset.local_path is None


def test_batch_varies_hook_and_motif_together(
    pain_point: PainPoint, campaign: CampaignConfig, brand_guide: BrandGuide, settings: Settings
) -> None:
    """Two variants of one pain point must differ on both axes, not just one."""
    pipeline = CreativePipeline(_llm(), MockImageProvider(brand_guide), brand_guide, settings)
    assets = pipeline.generate_batch([pain_point], campaign, variants_per_point=2)

    assert len(assets) == 2
    assert assets[0].dna.hook_type != assets[1].dna.hook_type
    assert assets[0].dna.visual_motif != assets[1].dna.visual_motif
    assert assets[0].dna.dna_id != assets[1].dna.dna_id


def test_image_prompt_carries_the_palette_and_tone(brand_guide: BrandGuide) -> None:
    """Stating brand constraints up front is cheaper than failing validation."""
    dna = CreativeDNA(
        hook_type="specific_number",
        pain_point_id="x",
        format="static",
        visual_motif="an oversized number",
        cta_style="LEARN_MORE",
    )
    prompt = build_image_prompt(AdCopy(**COPY_JSON), dna, brand_guide)

    assert brand_guide.palette[0].hex in prompt
    assert "an oversized number" in prompt
    assert COPY_JSON["hook"] in prompt


def test_video_script_splits_into_standalone_segments(pain_point: PainPoint) -> None:
    scripts = build_video_script(AdCopy(**COPY_JSON), pain_point, segments=3)
    assert 1 <= len(scripts) <= 3
    assert scripts[0] == COPY_JSON["hook"]  # the hook always leads


def test_stitcher_reports_missing_ffmpeg_clearly() -> None:
    """A host without ffmpeg must produce an actionable error, not a subprocess trace."""
    stitcher = VideoStitcher(ffmpeg_binary="definitely-not-a-real-binary")
    assert not stitcher.available
    with pytest.raises(FFmpegUnavailableError, match="not found on PATH"):
        stitcher.stitch([Path("a.mp4")], Path("out.mp4"))


def test_stitcher_rejects_an_empty_segment_list() -> None:
    stitcher = VideoStitcher()
    if not stitcher.available:
        pytest.skip("ffmpeg not installed")
    with pytest.raises(ValueError, match="no segments"):
        stitcher.stitch([], Path("out.mp4"))
