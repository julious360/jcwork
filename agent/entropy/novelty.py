"""The novelty gate.

An agent that iterates only on its own winners converges. Each generation is seeded
by the last, variance shrinks, and eventually every ad is a slightly worse copy of
the same ad — performance decays with no obvious cause, because nothing broke.

This module is the structural fix. Every candidate concept is embedded and compared
against the concepts already shipped; anything above the similarity threshold is
rejected before it can be published. Novelty is enforced, not hoped for.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.creative.models import CreativeDNA
from agent.llm import LLMClient, cosine_similarity
from agent.logging_setup import get_logger
from agent.ops.db import Database

log = get_logger(__name__)


@dataclass(slots=True)
class NoveltyVerdict:
    is_novel: bool
    max_similarity: float
    closest_summary: str = ""

    @property
    def reason(self) -> str:
        if self.is_novel:
            return f"novel (max similarity {self.max_similarity:.3f})"
        return (
            f"too similar to a shipped concept "
            f"(similarity {self.max_similarity:.3f}): {self.closest_summary[:120]}"
        )


class NoveltyGate:
    def __init__(
        self,
        db: Database,
        llm: LLMClient,
        threshold: float = 0.88,
        history_size: int = 50,
    ) -> None:
        self._db = db
        self._llm = llm
        self._threshold = threshold
        self._history_size = history_size

    def _recent(self) -> list[tuple[str, list[float]]]:
        with self._db.cursor() as cur:
            cur.execute(
                "SELECT summary, embedding FROM shipped_concepts ORDER BY shipped_at DESC LIMIT %s",
                (self._history_size,),
            )
            rows = cur.fetchall()
        return [(str(r["summary"]), [float(v) for v in r["embedding"]]) for r in rows]

    def check(self, dna: CreativeDNA) -> NoveltyVerdict:
        summary = dna.summary()
        embedding = self._llm.embed(summary)
        history = self._recent()

        if not history:
            return NoveltyVerdict(is_novel=True, max_similarity=0.0)

        best_score = 0.0
        best_summary = ""
        for past_summary, past_embedding in history:
            score = cosine_similarity(embedding, past_embedding)
            if score > best_score:
                best_score, best_summary = score, past_summary

        verdict = NoveltyVerdict(
            is_novel=best_score < self._threshold,
            max_similarity=round(best_score, 4),
            closest_summary=best_summary,
        )
        if not verdict.is_novel:
            log.info("entropy.concept_rejected", dna_id=dna.dna_id, reason=verdict.reason)
        return verdict

    def record_shipped(self, dna: CreativeDNA) -> None:
        """Register a concept as shipped so future candidates are measured against it."""
        summary = dna.summary()
        embedding = self._llm.embed(summary)
        with self._db.cursor() as cur:
            cur.execute(
                "INSERT INTO shipped_concepts "
                "(dna_id, concept_family_id, summary, embedding, is_external_dna) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    dna.dna_id,
                    dna.concept_family_id,
                    summary,
                    # psycopg adapts a Python list to float8[]. Do NOT json.dumps
                    # here: Postgres array literals use {} and would reject "[...]".
                    embedding,
                    dna.is_external,
                ),
            )
        log.info("entropy.concept_shipped", dna_id=dna.dna_id, family=dna.concept_family_id)

    def filter_novel(self, candidates: list[CreativeDNA]) -> list[CreativeDNA]:
        """Keep only novel candidates, also de-duplicating within the batch itself.

        Without the in-batch check, a single generation could ship six near-identical
        concepts simultaneously — each one novel against history, none against each
        other.
        """
        accepted: list[CreativeDNA] = []
        accepted_embeddings: list[list[float]] = []

        for candidate in candidates:
            verdict = self.check(candidate)
            if not verdict.is_novel:
                continue

            embedding = self._llm.embed(candidate.summary())
            if any(
                cosine_similarity(embedding, existing) >= self._threshold
                for existing in accepted_embeddings
            ):
                log.info("entropy.batch_duplicate_rejected", dna_id=candidate.dna_id)
                continue

            accepted.append(candidate)
            accepted_embeddings.append(embedding)

        return accepted
