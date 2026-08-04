"""Ad copy generation from ranked pain points.

Copy is generated per (pain point x hook type). Hook type is what makes two ads
genuinely different rather than reworded — it is also the primary axis the
anti-entropy layer tracks.
"""

from __future__ import annotations

from agent.config import CampaignConfig
from agent.creative.models import AdCopy
from agent.llm import LLMClient, LLMError
from agent.logging_setup import get_logger
from agent.research.models import PainPoint

log = get_logger(__name__)

# Distinct angles on the same problem. Cycling these is the cheapest real source of
# creative variance the agent has.
HOOK_TYPES = [
    "problem_agitation",
    "before_after",
    "contrarian_take",
    "specific_number",
    "customer_quote",
    "cost_of_inaction",
]

COPY_SYSTEM = """You write direct-response advertising that sounds like a person, \
not a brand.

Rules:
- Lead with the reader's problem, never with the product.
- Use the customer's own vocabulary from the supplied quotes.
- Be concrete. Numbers and specifics beat adjectives.
- No hype, no exclamation marks, no "revolutionary" or "game-changing".
- Never make a claim the product cannot support."""

COPY_PROMPT = """Write one Facebook ad.

PRODUCT: {product}
WHAT IT DOES: {value_prop}
AUDIENCE: {icp}

PROBLEM TO LEAD WITH: {problem}
WHAT THEY WANT INSTEAD: {outcome}

HOW REAL CUSTOMERS DESCRIBE IT:
{quotes}

HOOK ANGLE: {hook_type}
{hook_guidance}

Return JSON exactly in this shape:
{{
  "hook": "first line, under 12 words, stops the scroll",
  "primary_text": "2-4 short sentences, under 125 words",
  "headline": "under 40 characters",
  "description": "under 30 characters",
  "cta": "one of LEARN_MORE, SIGN_UP, GET_STARTED, BOOK_TRAVEL, DOWNLOAD"
}}
"""

HOOK_GUIDANCE = {
    "problem_agitation": (
        "Name the problem so precisely the reader feels seen. Do not resolve it in the hook."
    ),
    "before_after": "Contrast the current painful state with the specific desired state.",
    "contrarian_take": (
        "Challenge a belief the audience holds about this problem. Earn it — do not be "
        "edgy for its own sake."
    ),
    "specific_number": "Anchor on one concrete quantity: hours lost, percentage, dollar figure.",
    "customer_quote": "Open with a verbatim customer line, in quotation marks.",
    "cost_of_inaction": "Make the ongoing price of doing nothing tangible and near-term.",
}


class Copywriter:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def write(self, pain_point: PainPoint, campaign: CampaignConfig, hook_type: str) -> AdCopy:
        prompt = COPY_PROMPT.format(
            product=campaign.product_name,
            value_prop=campaign.value_proposition,
            icp=campaign.icp_description,
            problem=pain_point.problem,
            outcome=pain_point.desired_outcome,
            quotes="\n".join(f"- {q}" for q in pain_point.supporting_quotes) or "(none)",
            hook_type=hook_type,
            hook_guidance=HOOK_GUIDANCE.get(hook_type, ""),
        )
        raw = self._llm.complete_json(prompt, system=COPY_SYSTEM)
        try:
            return AdCopy(
                hook=str(raw["hook"]),
                primary_text=str(raw["primary_text"]),
                headline=str(raw["headline"]),
                description=str(raw.get("description", "")),
                cta=str(raw.get("cta", "LEARN_MORE")),
                pain_point_id=pain_point.id,
            )
        except KeyError as exc:
            raise LLMError(f"copy response missing required field: {exc}") from exc

    def write_variants(
        self, pain_point: PainPoint, campaign: CampaignConfig, hook_types: list[str] | None = None
    ) -> list[tuple[str, AdCopy]]:
        """One ad per hook angle, failures skipped rather than fatal."""
        results: list[tuple[str, AdCopy]] = []
        for hook_type in hook_types or HOOK_TYPES[:3]:
            try:
                results.append((hook_type, self.write(pain_point, campaign, hook_type)))
            except LLMError as exc:
                log.warning(
                    "creative.copy_failed", pain_point=pain_point.id, hook=hook_type, error=str(exc)
                )
        return results
