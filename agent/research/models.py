"""Research output schemas.

The ranked ``PainPointReport`` is the contract between research and the creative
engine. Everything downstream reads these fields, so provider differences stop here.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


class SourceDocument(BaseModel):
    """One raw statement of pain, as harvested."""

    provider: str
    url: str = ""
    title: str = ""
    body: str
    score: int = 0
    created_at: datetime | None = None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.body.strip().lower().encode()).hexdigest()[:32]


class PainPoint(BaseModel):
    """A ranked customer problem, with the evidence behind it."""

    id: str
    problem: str
    desired_outcome: str

    # Ranking inputs, all 0-1. Kept separate rather than pre-multiplied so a weak
    # score can be traced to the dimension that caused it.
    frequency: float = Field(ge=0.0, le=1.0)
    emotional_intensity: float = Field(ge=0.0, le=1.0)
    commercial_intent: float = Field(ge=0.0, le=1.0)

    supporting_quotes: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)

    @property
    def score(self) -> float:
        """Multiplicative on purpose: a zero on any dimension should sink the point.

        A problem everyone mentions but nobody would pay to solve is not an ad.
        """
        return self.frequency * self.emotional_intensity * self.commercial_intent

    @field_validator("supporting_quotes")
    @classmethod
    def _trim_quotes(cls, value: list[str]) -> list[str]:
        return [quote.strip() for quote in value if quote.strip()][:5]


class PainPointReport(BaseModel):
    category: str
    provider: str
    pain_points: list[PainPoint]
    documents_analyzed: int = 0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def ranked(self) -> list[PainPoint]:
        return sorted(self.pain_points, key=lambda p: p.score, reverse=True)

    def top(self, n: int = 3) -> list[PainPoint]:
        return self.ranked[:n]

    def content_hash(self) -> str:
        joined = "|".join(sorted(p.problem.lower().strip() for p in self.pain_points))
        return hashlib.sha256(f"{self.category}|{joined}".encode()).hexdigest()[:32]
