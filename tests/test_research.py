"""Research: fetching, clustering, and the ranking composite."""

from __future__ import annotations

from agent.config import CampaignConfig
from agent.llm import StubLLM, extract_json
from agent.research.models import PainPoint, PainPointReport, SourceDocument
from agent.research.providers import MockResearchProvider
from agent.research.ranker import PainPointRanker, report_to_json

CLUSTER_RESPONSE = {
    "pain_points": [
        {
            "id": "status_chasing",
            "problem": "Clients constantly ask for status updates",
            "desired_outcome": "Clients can see status without asking",
            "emotional_intensity": 0.8,
            "commercial_intent": 0.7,
            "document_indices": [0, 1],
            "supporting_quotes": ["I spend the first two hours of every day"],
        },
        {
            "id": "margin_blind",
            "problem": "No visibility into which projects are profitable",
            "desired_outcome": "Know margin per project in real time",
            "emotional_intensity": 0.9,
            "commercial_intent": 0.95,
            "document_indices": [2],
            "supporting_quotes": ["I genuinely cannot tell you which were profitable"],
        },
        {
            "id": "minor_gripe",
            "problem": "Mildly annoying UI",
            "desired_outcome": "Nicer UI",
            "emotional_intensity": 0.2,
            "commercial_intent": 0.05,
            "document_indices": [3, 4, 5],
            "supporting_quotes": [],
        },
    ]
}


def test_mock_provider_templates_the_configured_category(campaign: CampaignConfig) -> None:
    documents = MockResearchProvider().fetch(campaign)
    assert documents
    assert all("{category}" not in doc.body for doc in documents)
    assert any(campaign.product_category in doc.body for doc in documents)


def test_documents_are_deduplicated(campaign: CampaignConfig) -> None:
    duplicate = SourceDocument(provider="t", body="the same body text repeated here")
    ranker = PainPointRanker(StubLLM({"json": {"pain_points": []}}))
    report = ranker.rank([duplicate, duplicate, duplicate], campaign, "t")
    assert report.documents_analyzed == 1


def test_ranking_is_multiplicative_so_zero_intent_sinks_a_point(
    campaign: CampaignConfig,
) -> None:
    """A widely-echoed gripe nobody would pay to fix must not outrank a real problem."""
    documents = MockResearchProvider().fetch(campaign)
    report = PainPointRanker(StubLLM({"json": CLUSTER_RESPONSE})).rank(documents, campaign, "mock")

    ranked = report.ranked
    assert [p.id for p in ranked][:2] == ["status_chasing", "margin_blind"]
    # minor_gripe appears in the most documents, yet ranks last.
    assert ranked[-1].id == "minor_gripe"


def test_frequency_is_measured_not_asserted_by_the_model(campaign: CampaignConfig) -> None:
    documents = MockResearchProvider().fetch(campaign)
    report = PainPointRanker(StubLLM({"json": CLUSTER_RESPONSE})).rank(documents, campaign, "mock")
    by_id = {p.id: p for p in report.pain_points}
    # Three supporting documents versus one: frequency must reflect that.
    assert by_id["minor_gripe"].frequency > by_id["margin_blind"].frequency


def test_top_n_returns_requested_count(campaign: CampaignConfig) -> None:
    documents = MockResearchProvider().fetch(campaign)
    report = PainPointRanker(StubLLM({"json": CLUSTER_RESPONSE})).rank(documents, campaign, "mock")
    assert len(report.top(3)) == 3
    assert len(report.top(2)) == 2


def test_report_json_is_valid_and_ordered(campaign: CampaignConfig) -> None:
    import json

    documents = MockResearchProvider().fetch(campaign)
    report = PainPointRanker(StubLLM({"json": CLUSTER_RESPONSE})).rank(documents, campaign, "mock")
    parsed = json.loads(report_to_json(report, 3))

    assert parsed["category"] == campaign.product_category
    assert [p["rank"] for p in parsed["top_pain_points"]] == [1, 2, 3]
    scores = [p["score"] for p in parsed["top_pain_points"]]
    assert scores == sorted(scores, reverse=True)


def test_empty_document_set_produces_an_empty_report(campaign: CampaignConfig) -> None:
    report = PainPointRanker(StubLLM()).rank([], campaign, "mock")
    assert report.pain_points == []
    assert report.top(3) == []


def test_malformed_llm_output_is_survived(campaign: CampaignConfig) -> None:
    """One bad cluster entry must not discard the whole run."""
    broken = {"pain_points": [{"no_problem_field": True}, CLUSTER_RESPONSE["pain_points"][0]]}
    documents = MockResearchProvider().fetch(campaign)
    report = PainPointRanker(StubLLM({"json": broken})).rank(documents, campaign, "mock")
    assert len(report.pain_points) == 1


def test_pain_point_score_is_the_product_of_its_dimensions() -> None:
    point = PainPoint(
        id="x",
        problem="p",
        desired_outcome="o",
        frequency=0.5,
        emotional_intensity=0.8,
        commercial_intent=0.5,
    )
    assert abs(point.score - 0.2) < 1e-9


def test_report_content_hash_is_stable_across_ordering() -> None:
    def build(order: list[str]) -> PainPointReport:
        return PainPointReport(
            category="c",
            provider="p",
            pain_points=[
                PainPoint(
                    id=name,
                    problem=name,
                    desired_outcome="",
                    frequency=0.5,
                    emotional_intensity=0.5,
                    commercial_intent=0.5,
                )
                for name in order
            ],
        )

    assert build(["a", "b"]).content_hash() == build(["b", "a"]).content_hash()


def test_extract_json_handles_fenced_and_prose_wrapped_output() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Here you go: {"a": 1} hope that helps') == {"a": 1}
