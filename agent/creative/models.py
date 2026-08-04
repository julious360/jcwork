"""Creative types shared across generation, validation, and publishing."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class AssetType(StrEnum):
    STATIC = "static"
    VIDEO = "video"


class AdCopy(BaseModel):
    hook: str
    primary_text: str
    headline: str
    description: str = ""
    cta: str = "LEARN_MORE"
    pain_point_id: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "hook": self.hook,
            "primary_text": self.primary_text,
            "headline": self.headline,
            "description": self.description,
            "cta": self.cta,
        }


class CreativeDNA(BaseModel):
    """The genes of a creative concept.

    Tracked explicitly so the anti-entropy layer can reason about what has already
    been tried and where a concept came from. ``is_external`` is the important one:
    it marks concepts seeded from outside our own account, which is what the
    exploration budget protects.
    """

    hook_type: str
    pain_point_id: str
    format: str
    visual_motif: str
    cta_style: str
    lineage: list[str] = Field(default_factory=list)
    is_external: bool = False
    source_ref: str = ""

    @property
    def dna_id(self) -> str:
        parts = "|".join(
            [self.hook_type, self.pain_point_id, self.format, self.visual_motif, self.cta_style]
        )
        return hashlib.sha256(parts.encode()).hexdigest()[:20]

    @property
    def concept_family_id(self) -> str:
        """Groups variants of the same underlying idea.

        Family is hook type plus pain point: change the visual and it is a variant,
        change the angle and it is a new family.
        """
        return hashlib.sha256(f"{self.hook_type}|{self.pain_point_id}".encode()).hexdigest()[:16]

    def summary(self) -> str:
        """Text form used for embedding and novelty comparison."""
        return (
            f"{self.hook_type} hook about {self.pain_point_id}, "
            f"{self.format} format, {self.visual_motif} visual, {self.cta_style} CTA"
        )


class ValidationIssue(BaseModel):
    check: str
    severity: str  # "error" blocks publication; "warning" is advisory
    detail: str


class ValidationResult(BaseModel):
    passed: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    palette_coverage_pct: float = 0.0
    checked_by: list[str] = Field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    def summary(self) -> str:
        if self.passed:
            return "passed"
        return "; ".join(f"[{i.check}] {i.detail}" for i in self.errors) or "failed"


class CreativeAsset(BaseModel):
    asset_type: AssetType
    dna: CreativeDNA
    # Named ad_copy rather than copy: BaseModel already defines .copy().
    ad_copy: AdCopy
    local_path: Path | None = None
    validation: ValidationResult | None = None
    status: str = "draft"
