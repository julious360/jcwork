"""Job handlers — the agent's actual work, one function per job kind.

The self-optimising loop is the chain:

    refresh_warehouse -> decision_loop
    harvest_entropy   -> research -> generate_creative -> (human or auto) publish

Each stage is a separate queued job so a slow creative generation cannot delay the
decision loop, and any stage can be retried in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from agent.config import (
    CampaignConfig,
    Settings,
    ThresholdConfig,
    load_brand_guide,
    load_campaign,
    load_thresholds,
)
from agent.creative.pipeline import VISUAL_MOTIFS, CreativePipeline
from agent.creative.providers import build_image_provider
from agent.decision.engine import DecisionEngine, default_lookback
from agent.entropy.dna import DNAPool, evaluate_exploration, next_batch_external_ratio
from agent.entropy.novelty import NoveltyGate
from agent.entropy.sources import GeneExtractor, build_harvesters
from agent.llm import build_llm
from agent.logging_setup import get_logger
from agent.meta.write_client import MetaWriteClient
from agent.ops.breaker import CircuitBreaker
from agent.ops.db import Database
from agent.ops.ledger import ActionLedger, IdempotencyStore
from agent.ops.queue import JobQueue
from agent.research.providers import build_provider
from agent.research.ranker import PainPointRanker
from agent.warehouse.client import WarehouseClient
from agent.warehouse.queries import WarehouseQueries

log = get_logger(__name__)

JOB_REFRESH_WAREHOUSE = "refresh_warehouse"
JOB_DECISION_LOOP = "decision_loop"
JOB_RESEARCH = "research"
JOB_GENERATE_CREATIVE = "generate_creative"
JOB_HARVEST_ENTROPY = "harvest_entropy"


@dataclass
class JobContext:
    """Wiring shared by every handler. Built once per worker process."""

    settings: Settings
    db: Database
    queue: JobQueue
    ledger: ActionLedger
    warehouse: WarehouseClient
    queries: WarehouseQueries
    campaign: CampaignConfig
    thresholds: ThresholdConfig

    @classmethod
    def build(cls, settings: Settings) -> JobContext:
        db = Database(settings)
        warehouse = WarehouseClient(settings)
        return cls(
            settings=settings,
            db=db,
            queue=JobQueue(db),
            ledger=ActionLedger(db),
            warehouse=warehouse,
            queries=WarehouseQueries(warehouse),
            campaign=load_campaign(),
            thresholds=load_thresholds(),
        )


def refresh_warehouse(ctx: JobContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the identity spine and the economics mart, then queue the loop."""
    days = int(payload.get("days", 30))
    end = date.today()
    start = end - timedelta(days=days)

    ctx.queries.rebuild_identity_bridge()
    ctx.queries.refresh_mart(start, end, ctx.thresholds.attribution)
    ctx.queue.enqueue(JOB_DECISION_LOOP, {"dry_run": payload.get("dry_run", True)})

    return {"start": str(start), "end": str(end)}


def decision_loop(ctx: JobContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Read the warehouse, decide, and (unless dry-running) write to Meta."""
    dry_run = bool(payload.get("dry_run", ctx.settings.meta.dry_run))
    since = default_lookback(ctx.thresholds)
    economics = ctx.queries.load_ad_economics(since)

    executor = None
    if not dry_run:
        breaker = CircuitBreaker(ctx.db)
        executor = MetaWriteClient(
            settings=ctx.settings,
            breaker=breaker,
            idempotency=IdempotencyStore(ctx.db),
        )

    engine = DecisionEngine(ctx.ledger, ctx.thresholds, executor)
    result = engine.run(economics, dry_run=dry_run)

    return {
        "run_id": str(result.run_id),
        "evaluated": result.evaluated,
        "actionable": len(result.actionable),
        "executed": result.executed,
        "failed": result.failed,
        "awaiting_approval": result.skipped_for_approval,
        "by_action": result.counts_by_action(),
    }


def research(ctx: JobContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Rank customer pain points and queue creative generation from them."""
    llm = build_llm(ctx.settings)
    provider = build_provider(ctx.settings)
    documents = provider.fetch(ctx.campaign, limit=int(payload.get("limit", 50)))
    report = PainPointRanker(llm).rank(documents, ctx.campaign, provider.name)

    top = report.top(ctx.campaign.top_pain_points)
    if top:
        ctx.queue.enqueue(
            JOB_GENERATE_CREATIVE,
            {"pain_points": [p.model_dump(mode="json") for p in top]},
        )

    return {
        "provider": provider.name,
        "documents": report.documents_analyzed,
        "pain_points": [{"id": p.id, "score": round(p.score, 4)} for p in top],
    }


def generate_creative(ctx: JobContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Generate candidates, gate them for novelty, and register what survives.

    Creative is always created PAUSED and recorded as an asset; publishing is a
    separate, deliberate step. An agent that generates and publishes in one motion
    can put an unreviewed image in front of customers.
    """
    from agent.research.models import PainPoint

    pain_points = [PainPoint(**item) for item in payload.get("pain_points", [])]
    if not pain_points:
        return {"generated": 0, "reason": "no pain points supplied"}

    llm = build_llm(ctx.settings)
    guide = load_brand_guide()
    pipeline = CreativePipeline(llm, build_image_provider(ctx.settings, guide), guide, ctx.settings)
    gate = NoveltyGate(
        ctx.db, llm, ctx.thresholds.novelty_threshold, ctx.thresholds.novelty_history_size
    )
    pool = DNAPool(ctx.db, llm)

    # How much of this batch should be externally seeded, given where the
    # exploration budget currently stands.
    split = ctx.queries.concept_spend_split()
    status = evaluate_exploration(
        split["external"], split["internal"], ctx.thresholds.exploration_pct
    )
    external_ratio = next_batch_external_ratio(status)
    log.info("entropy.exploration_status", detail=status.describe(), next_ratio=external_ratio)

    variants = int(payload.get("variants_per_point", 2) or 2)
    total = len(pain_points) * variants
    external_target = round(total * external_ratio)
    genes = pool.draw(count=external_target) if external_target else []

    generated: list[dict[str, Any]] = []
    index = 0
    for pain_point in pain_points:
        for _ in range(variants):
            gene = genes[index] if index < len(genes) else None
            hook = gene.hook_type if gene else _rotate(index)
            motif = gene.visual_motif if gene else VISUAL_MOTIFS[index % len(VISUAL_MOTIFS)]

            asset = pipeline.generate_static(
                pain_point=pain_point,
                campaign=ctx.campaign,
                hook_type=hook,
                motif=motif,
                external_dna=gene is not None,
                source_ref=gene.source_ref if gene else "",
            )

            verdict = gate.check(asset.dna)
            if not verdict.is_novel:
                asset.status = "rejected"
            elif asset.status == "validated":
                gate.record_shipped(asset.dna)

            _persist_asset(ctx, asset, verdict.max_similarity)
            generated.append(
                {
                    "dna_id": asset.dna.dna_id,
                    "status": asset.status,
                    "hook": asset.dna.hook_type,
                    "external": asset.dna.is_external,
                    "novelty": verdict.max_similarity,
                }
            )
            index += 1

    return {
        "generated": len(generated),
        "validated": sum(1 for a in generated if a["status"] == "validated"),
        "rejected": sum(1 for a in generated if a["status"] == "rejected"),
        "needs_review": sum(1 for a in generated if a["status"] == "needs_review"),
        "exploration": status.describe(),
        "assets": generated,
    }


def harvest_entropy(ctx: JobContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Pull fresh external DNA into the pool."""
    llm = build_llm(ctx.settings)
    extractor = GeneExtractor(llm)
    pool = DNAPool(ctx.db, llm)

    harvested_counts: dict[str, int] = {}
    all_genes = []
    for harvester in build_harvesters(ctx.settings):
        items = harvester.harvest(ctx.campaign, limit=int(payload.get("limit", 20)))
        harvested_counts[harvester.name] = len(items)
        for item in items:
            all_genes.extend(extractor.extract(item))

    added = pool.add(all_genes) if all_genes else 0
    return {
        "harvested": harvested_counts,
        "genes_extracted": len(all_genes),
        "genes_added": added,
        "pool_size": pool.size(),
    }


HANDLERS = {
    JOB_REFRESH_WAREHOUSE: refresh_warehouse,
    JOB_DECISION_LOOP: decision_loop,
    JOB_RESEARCH: research,
    JOB_GENERATE_CREATIVE: generate_creative,
    JOB_HARVEST_ENTROPY: harvest_entropy,
}


def _rotate(index: int) -> str:
    from agent.creative.copywriter import HOOK_TYPES

    return HOOK_TYPES[index % len(HOOK_TYPES)]


def _persist_asset(ctx: JobContext, asset: Any, novelty: float) -> None:
    with ctx.db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO creative_assets
                (asset_type, dna_id, concept_family_id, pain_point_id,
                 local_path, copy, validation, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(asset.asset_type),
                asset.dna.dna_id,
                asset.dna.concept_family_id,
                asset.dna.pain_point_id,
                str(asset.local_path) if asset.local_path else None,
                _json(asset.ad_copy.as_dict()),
                _json(
                    {
                        "novelty_similarity": novelty,
                        "result": asset.validation.model_dump(mode="json")
                        if asset.validation
                        else None,
                    }
                ),
                asset.status,
            ),
        )


def _json(value: Any) -> str:
    import json

    return json.dumps(value, default=str)


def budget_from(value: Any) -> Decimal:
    return Decimal(str(value))
