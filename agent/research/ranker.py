"""Cluster raw documents into pain points and rank them.

Frequency is computed in code from actual document counts; only the two judgement
calls — how much this hurts, and whether someone would pay to stop it — go to the
model. Letting an LLM invent all three scores produces confident numbers with
nothing behind them.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agent.config import CampaignConfig
from agent.llm import LLMClient, LLMError
from agent.logging_setup import get_logger
from agent.research.models import PainPoint, PainPointReport, SourceDocument

log = get_logger(__name__)

CLUSTER_SYSTEM = """You analyse unfiltered customer complaints and identify the \
underlying problems they share.

Rules:
- Work only from the supplied documents. Never invent a problem that is not evidenced.
- State each problem in the customer's own framing, not marketing language.
- Quote verbatim. Do not paraphrase quotes.
- emotional_intensity: how much distress the language actually conveys (0-1).
- commercial_intent: how likely someone is to pay to solve this (0-1). A widely \
mentioned annoyance nobody would buy a solution for scores low.
"""

CLUSTER_PROMPT = """Product category: {category}
Ideal customer: {icp}

Identify the {n} distinct core problems below. Return JSON exactly in this shape:

{{
  "pain_points": [
    {{
      "id": "short_snake_case_id",
      "problem": "the problem in the customer's framing",
      "desired_outcome": "what they want to be true instead",
      "emotional_intensity": 0.0,
      "commercial_intent": 0.0,
      "document_indices": [0, 3],
      "supporting_quotes": ["verbatim quote", "verbatim quote"]
    }}
  ]
}}

Documents:
{documents}
"""


class PainPointRanker:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def rank(
        self,
        documents: list[SourceDocument],
        campaign: CampaignConfig,
        provider: str,
        cluster_count: int = 5,
    ) -> PainPointReport:
        deduped = _dedupe(documents)
        if not deduped:
            log.warning("research.no_documents")
            return PainPointReport(
                category=campaign.product_category, provider=provider, pain_points=[]
            )

        rendered = "\n\n".join(
            f"[{i}] (score {doc.score}) {doc.title}\n{doc.body[:1500]}"
            for i, doc in enumerate(deduped)
        )
        prompt = CLUSTER_PROMPT.format(
            category=campaign.product_category,
            icp=campaign.icp_description,
            n=cluster_count,
            documents=rendered,
        )

        try:
            raw = self._llm.complete_json(prompt, system=CLUSTER_SYSTEM)
        except LLMError as exc:
            log.error("research.clustering_failed", error=str(exc))
            return PainPointReport(
                category=campaign.product_category,
                provider=provider,
                pain_points=[],
                documents_analyzed=len(deduped),
            )

        pain_points = self._build_pain_points(raw, deduped)
        report = PainPointReport(
            category=campaign.product_category,
            provider=provider,
            pain_points=pain_points,
            documents_analyzed=len(deduped),
        )
        log.info(
            "research.ranked",
            category=campaign.product_category,
            documents=len(deduped),
            pain_points=len(pain_points),
        )
        return report

    def _build_pain_points(
        self, raw: dict[str, Any], documents: list[SourceDocument]
    ) -> list[PainPoint]:
        results: list[PainPoint] = []
        total = len(documents) or 1

        for item in raw.get("pain_points", []):
            indices = [i for i in item.get("document_indices", []) if 0 <= int(i) < total]

            # Frequency is measured, not asked for: the share of documents that
            # actually evidence this cluster, nudged by community score so a problem
            # 400 people upvoted outranks one mentioned twice in passing.
            share = len(indices) / total
            engagement = sum(documents[int(i)].score for i in indices)
            max_engagement = max((doc.score for doc in documents), default=0) * total or 1
            frequency = min(1.0, 0.7 * share + 0.3 * (engagement / max_engagement))

            try:
                results.append(
                    PainPoint(
                        id=_slug(item.get("id") or item.get("problem", "unknown")),
                        problem=str(item["problem"]),
                        desired_outcome=str(item.get("desired_outcome", "")),
                        frequency=round(frequency, 4),
                        emotional_intensity=_clamp(item.get("emotional_intensity", 0.5)),
                        commercial_intent=_clamp(item.get("commercial_intent", 0.5)),
                        supporting_quotes=list(item.get("supporting_quotes", [])),
                        source_urls=[
                            documents[int(i)].url for i in indices if documents[int(i)].url
                        ],
                    )
                )
            except (KeyError, ValueError) as exc:
                log.warning("research.pain_point_skipped", error=str(exc))
        return results


def _dedupe(documents: list[SourceDocument]) -> list[SourceDocument]:
    seen: set[str] = set()
    unique: list[SourceDocument] = []
    for doc in documents:
        if doc.content_hash in seen:
            continue
        seen.add(doc.content_hash)
        unique.append(doc)
    return unique


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return slug[:60] or "unknown"


def report_to_json(report: PainPointReport, top_n: int = 3) -> str:
    """The ranked top-N as JSON — the handoff into the creative engine."""
    return json.dumps(
        {
            "category": report.category,
            "provider": report.provider,
            "generated_at": report.generated_at.isoformat(),
            "documents_analyzed": report.documents_analyzed,
            "top_pain_points": [
                {
                    "rank": i + 1,
                    "id": p.id,
                    "problem": p.problem,
                    "desired_outcome": p.desired_outcome,
                    "score": round(p.score, 4),
                    "frequency": p.frequency,
                    "emotional_intensity": p.emotional_intensity,
                    "commercial_intent": p.commercial_intent,
                    "supporting_quotes": p.supporting_quotes,
                    "source_urls": p.source_urls,
                }
                for i, p in enumerate(report.top(top_n))
            ],
        },
        indent=2,
    )
