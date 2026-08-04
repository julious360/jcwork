"""The creative pipeline: ranked pain points in, validated ad assets out.

The generate -> validate -> regenerate loop is bounded. After
``max_validation_attempts`` the asset is marked ``needs_review`` and handed to a
human rather than either shipped unvalidated or silently dropped.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from agent.config import BrandGuide, CampaignConfig, Settings, get_settings
from agent.creative.brand_validator import issues_as_feedback, validate_creative
from agent.creative.copywriter import HOOK_TYPES, Copywriter
from agent.creative.models import AdCopy, AssetType, CreativeAsset, CreativeDNA
from agent.creative.providers import ImageProvider, build_image_prompt
from agent.llm import LLMClient
from agent.logging_setup import get_logger
from agent.research.models import PainPoint

log = get_logger(__name__)

VISUAL_MOTIFS = [
    "a cluttered desk shot from above, one item in sharp focus",
    "a split composition contrasting chaos and calm",
    "a single oversized number as the hero element",
    "an empty meeting room with one chair turned out",
    "hands mid-gesture over a laptop, face out of frame",
    "a clean abstract diagram of a workflow",
]


class CreativePipeline:
    def __init__(
        self,
        llm: LLMClient,
        image_provider: ImageProvider,
        guide: BrandGuide,
        settings: Settings | None = None,
    ) -> None:
        self._llm = llm
        self._images = image_provider
        self._guide = guide
        self._settings = settings or get_settings()
        self._copywriter = Copywriter(llm)

    def generate_static(
        self,
        pain_point: PainPoint,
        campaign: CampaignConfig,
        hook_type: str,
        motif: str,
        external_dna: bool = False,
        source_ref: str = "",
    ) -> CreativeAsset:
        ad_copy = self._copywriter.write(pain_point, campaign, hook_type)
        dna = CreativeDNA(
            hook_type=hook_type,
            pain_point_id=pain_point.id,
            format="static",
            visual_motif=motif,
            cta_style=ad_copy.cta,
            is_external=external_dna,
            source_ref=source_ref,
        )
        asset = CreativeAsset(asset_type=AssetType.STATIC, dna=dna, ad_copy=ad_copy)
        return self._render_and_validate(asset, campaign)

    def _render_and_validate(self, asset: CreativeAsset, campaign: CampaignConfig) -> CreativeAsset:
        artifact_dir = self._settings.creative.artifact_dir
        max_attempts = self._settings.creative.max_validation_attempts
        prompt = build_image_prompt(asset.ad_copy, asset.dna, self._guide)
        feedback = ""

        for attempt in range(1, max_attempts + 1):
            path = artifact_dir / f"{asset.dna.dna_id}_{uuid.uuid4().hex[:8]}.png"
            try:
                self._images.generate(prompt + feedback, path)
            except Exception as exc:
                log.warning("creative.generation_failed", attempt=attempt, error=str(exc))
                continue

            result = validate_creative(path, self._guide, self._llm)
            asset.local_path = path
            asset.validation = result

            if result.passed:
                asset.status = "validated"
                log.info(
                    "creative.validated",
                    dna_id=asset.dna.dna_id,
                    attempt=attempt,
                    palette_coverage=result.palette_coverage_pct,
                )
                return asset

            log.info(
                "creative.validation_failed",
                dna_id=asset.dna.dna_id,
                attempt=attempt,
                reason=result.summary(),
            )
            # Feed the specific failures back into the next attempt rather than
            # re-rolling blindly.
            feedback = (
                f"\n\nThe previous attempt was rejected. Fix these specific problems:\n"
                f"{issues_as_feedback(result)}"
            )

        asset.status = "needs_review"
        log.warning("creative.needs_human_review", dna_id=asset.dna.dna_id)
        return asset

    def generate_batch(
        self,
        pain_points: list[PainPoint],
        campaign: CampaignConfig,
        variants_per_point: int = 2,
    ) -> list[CreativeAsset]:
        """One batch of candidates across pain points, hooks, and motifs.

        Hook and motif are advanced together so two variants of the same pain point
        differ on both axes — varying only one produces near-duplicates that the
        novelty gate would reject anyway.
        """
        assets: list[CreativeAsset] = []
        for point_index, pain_point in enumerate(pain_points):
            for variant in range(variants_per_point):
                offset = point_index * variants_per_point + variant
                assets.append(
                    self.generate_static(
                        pain_point=pain_point,
                        campaign=campaign,
                        hook_type=HOOK_TYPES[offset % len(HOOK_TYPES)],
                        motif=VISUAL_MOTIFS[offset % len(VISUAL_MOTIFS)],
                    )
                )
        return assets


def build_video_script(ad_copy: AdCopy, pain_point: PainPoint, segments: int = 3) -> list[str]:
    """Split ad copy into per-segment avatar scripts.

    Structured as hook / problem / resolution so each segment stands alone if the
    viewer drops off, which most do within the first three seconds.
    """
    sentences = [s.strip() for s in ad_copy.primary_text.split(".") if s.strip()]
    scripts = [ad_copy.hook]

    if sentences:
        chunk = max(1, len(sentences) // max(1, segments - 1))
        for i in range(0, len(sentences), chunk):
            scripts.append(". ".join(sentences[i : i + chunk]) + ".")

    return scripts[:segments] or [ad_copy.hook]


def asset_artifact_paths(assets: list[CreativeAsset]) -> list[Path]:
    return [a.local_path for a in assets if a.local_path is not None]
