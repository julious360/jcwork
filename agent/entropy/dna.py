"""The DNA pool and the exploration budget.

Two jobs:

* Store creative genes harvested from outside our own account, so the creative
  engine has raw material it did not generate itself.
* Enforce that a real share of spend actually goes to those externally-seeded
  concepts. A reservoir the agent never draws from changes nothing — the budget
  floor is what converts stored novelty into shipped novelty.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal

from agent.creative.models import CreativeDNA
from agent.llm import LLMClient
from agent.logging_setup import get_logger
from agent.ops.db import Database

log = get_logger(__name__)


@dataclass(slots=True)
class DNAGene:
    source: str
    source_ref: str
    hook_type: str
    visual_motif: str
    cta_style: str
    raw_excerpt: str
    is_external: bool = True

    @property
    def content_hash(self) -> str:
        payload = f"{self.source}|{self.hook_type}|{self.visual_motif}|{self.raw_excerpt[:200]}"
        return hashlib.sha256(payload.encode()).hexdigest()[:32]


class DNAPool:
    def __init__(self, db: Database, llm: LLMClient) -> None:
        self._db = db
        self._llm = llm

    def add(self, genes: list[DNAGene]) -> int:
        """Store genes, skipping ones already present. Returns the number added."""
        added = 0
        with self._db.cursor() as cur:
            for gene in genes:
                embedding = self._llm.embed(
                    f"{gene.hook_type} {gene.visual_motif} {gene.raw_excerpt[:400]}"
                )
                cur.execute(
                    """
                    INSERT INTO dna_pool
                        (source, source_ref, hook_type, visual_motif, cta_style,
                         raw_excerpt, embedding, is_external, content_hash)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (content_hash) DO NOTHING
                    RETURNING id
                    """,
                    (
                        gene.source,
                        gene.source_ref,
                        gene.hook_type,
                        gene.visual_motif,
                        gene.cta_style,
                        gene.raw_excerpt[:4000],
                        # psycopg adapts a list to float8[]; json.dumps would emit
                        # "[...]" which is not valid Postgres array syntax.
                        embedding,
                        gene.is_external,
                        gene.content_hash,
                    ),
                )
                if cur.fetchone() is not None:
                    added += 1
        log.info("entropy.dna_added", offered=len(genes), added=added)
        return added

    def draw(self, count: int = 5, external_only: bool = True) -> list[DNAGene]:
        """Draw the least-used genes first, so the pool is worked through evenly.

        Ordering by ``used_count`` rather than randomly matters: random draws
        re-select the same handful of genes and reintroduce the monoculture the pool
        exists to prevent.
        """
        with self._db.cursor() as cur:
            cur.execute(
                """
                SELECT id, source, source_ref, hook_type, visual_motif, cta_style,
                       raw_excerpt, is_external
                FROM dna_pool
                WHERE (%s = FALSE OR is_external = TRUE)
                ORDER BY used_count ASC, created_at DESC
                LIMIT %s
                """,
                (external_only, count),
            )
            rows = cur.fetchall()

            if rows:
                cur.execute(
                    "UPDATE dna_pool SET used_count = used_count + 1 WHERE id = ANY(%s)",
                    ([int(r["id"]) for r in rows],),
                )

        return [
            DNAGene(
                source=str(r["source"]),
                source_ref=str(r["source_ref"] or ""),
                hook_type=str(r["hook_type"] or "problem_agitation"),
                visual_motif=str(r["visual_motif"] or ""),
                cta_style=str(r["cta_style"] or "LEARN_MORE"),
                raw_excerpt=str(r["raw_excerpt"] or ""),
                is_external=bool(r["is_external"]),
            )
            for r in rows
        ]

    def size(self, external_only: bool = True) -> int:
        with self._db.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM dna_pool WHERE (%s = FALSE OR is_external = TRUE)",
                (external_only,),
            )
            row = cur.fetchone()
        return int(row["n"])  # type: ignore[index]


def gene_to_dna(gene: DNAGene, pain_point_id: str, fmt: str = "static") -> CreativeDNA:
    """Turn a harvested gene into a concept seed for the creative pipeline."""
    return CreativeDNA(
        hook_type=gene.hook_type,
        pain_point_id=pain_point_id,
        format=fmt,
        visual_motif=gene.visual_motif,
        cta_style=gene.cta_style,
        lineage=[f"{gene.source}:{gene.source_ref}"],
        is_external=gene.is_external,
        source_ref=gene.source_ref,
    )


@dataclass(slots=True)
class ExplorationStatus:
    external_spend: Decimal
    internal_spend: Decimal
    target_pct: float

    @property
    def total(self) -> Decimal:
        return self.external_spend + self.internal_spend

    @property
    def current_pct(self) -> float:
        if self.total <= 0:
            return 0.0
        return float(self.external_spend / self.total) * 100.0

    @property
    def is_satisfied(self) -> bool:
        return self.current_pct >= self.target_pct

    @property
    def shortfall_pct(self) -> float:
        return max(0.0, self.target_pct - self.current_pct)

    def describe(self) -> str:
        return (
            f"exploration at {self.current_pct:.1f}% of spend "
            f"(target {self.target_pct:.1f}%, "
            f"{'satisfied' if self.is_satisfied else 'SHORTFALL'})"
        )


def evaluate_exploration(
    external_spend: Decimal, internal_spend: Decimal, target_pct: float
) -> ExplorationStatus:
    return ExplorationStatus(
        external_spend=external_spend, internal_spend=internal_spend, target_pct=target_pct
    )


def next_batch_external_ratio(status: ExplorationStatus) -> float:
    """How much of the next creative batch should come from external DNA.

    When exploration is behind, the next batch over-corrects rather than merely
    meeting the target — otherwise a deficit accumulated during a winning streak is
    never actually repaid.
    """
    if status.is_satisfied:
        return status.target_pct / 100.0
    return min(1.0, (status.target_pct + status.shortfall_pct) / 100.0)
