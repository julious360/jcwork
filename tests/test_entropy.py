"""Anti-entropy: novelty gating and the exploration budget."""

from __future__ import annotations

from decimal import Decimal

from agent.creative.models import CreativeDNA
from agent.entropy.dna import DNAGene, evaluate_exploration, gene_to_dna, next_batch_external_ratio
from agent.entropy.novelty import NoveltyGate
from agent.llm import HashingEmbedder, StubLLM, cosine_similarity


class FakeCursor:
    def __init__(self, store: list[dict[str, object]]) -> None:
        self._store = store
        self._last: list[dict[str, object]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        if sql.strip().upper().startswith("SELECT"):
            self._last = list(reversed(self._store))
        else:
            # params[3] is the raw embedding list — psycopg adapts it to float8[]
            # and returns a list on read, so the fake stores it unchanged.
            self._store.append({"summary": params[2], "embedding": params[3]})

    def fetchall(self) -> list[dict[str, object]]:
        return self._last

    def fetchone(self) -> dict[str, object] | None:
        return self._last[0] if self._last else None


class FakeDB:
    """Minimal Database stand-in backed by a list."""

    def __init__(self) -> None:
        self.store: list[dict[str, object]] = []

    def cursor(self):  # type: ignore[no-untyped-def]
        from contextlib import contextmanager

        @contextmanager
        def _cursor():  # type: ignore[no-untyped-def]
            yield FakeCursor(self.store)

        return _cursor()


def _dna(hook: str, pain: str, motif: str) -> CreativeDNA:
    return CreativeDNA(
        hook_type=hook,
        pain_point_id=pain,
        format="static",
        visual_motif=motif,
        cta_style="LEARN_MORE",
    )


def test_embeddings_are_deterministic() -> None:
    embedder = HashingEmbedder()
    assert embedder.embed("hello world") == embedder.embed("hello world")


def test_identical_text_is_maximally_similar() -> None:
    embedder = HashingEmbedder()
    similarity = cosine_similarity(embedder.embed("a b c"), embedder.embed("a b c"))
    assert similarity > 0.999


def test_different_concepts_are_dissimilar() -> None:
    embedder = HashingEmbedder()
    a = embedder.embed("contrarian_take hook about margin blindness, chart visual")
    b = embedder.embed("customer_quote hook about status chasing, portrait visual")
    assert cosine_similarity(a, b) < 0.7


def test_first_concept_is_always_novel() -> None:
    gate = NoveltyGate(FakeDB(), StubLLM(), threshold=0.88)
    verdict = gate.check(_dna("contrarian_take", "margin", "a chart"))
    assert verdict.is_novel
    assert verdict.max_similarity == 0.0


def test_near_duplicate_is_rejected_after_shipping() -> None:
    db = FakeDB()
    gate = NoveltyGate(db, StubLLM(), threshold=0.88)
    dna = _dna("contrarian_take", "margin_blind", "a single oversized number")

    gate.record_shipped(dna)
    assert not gate.check(dna).is_novel


def test_genuinely_different_concept_still_passes() -> None:
    db = FakeDB()
    gate = NoveltyGate(db, StubLLM(), threshold=0.88)
    gate.record_shipped(_dna("contrarian_take", "margin_blind", "a single oversized number"))

    fresh = _dna("customer_quote", "status_chasing", "an empty meeting room")
    assert gate.check(fresh).is_novel


def test_batch_deduplication_catches_in_batch_clones() -> None:
    """Two identical candidates in one batch: only one may ship."""
    gate = NoveltyGate(FakeDB(), StubLLM(), threshold=0.88)
    dna = _dna("before_after", "onboarding", "split composition")
    accepted = gate.filter_novel([dna, dna, _dna("specific_number", "margin", "big number")])
    assert len(accepted) == 2


# ── Exploration budget ────────────────────────────────────────────────────────


def test_exploration_shortfall_is_detected() -> None:
    status = evaluate_exploration(Decimal("100"), Decimal("900"), target_pct=20.0)
    assert status.current_pct == 10.0
    assert not status.is_satisfied
    assert status.shortfall_pct == 10.0


def test_exploration_satisfied() -> None:
    status = evaluate_exploration(Decimal("300"), Decimal("700"), target_pct=20.0)
    assert status.is_satisfied
    assert status.shortfall_pct == 0.0


def test_no_spend_yet_reports_zero_not_divide_by_zero() -> None:
    status = evaluate_exploration(Decimal("0"), Decimal("0"), target_pct=20.0)
    assert status.current_pct == 0.0


def test_next_batch_overcorrects_when_behind() -> None:
    """A deficit must be repaid, not merely stopped from growing."""
    behind = evaluate_exploration(Decimal("50"), Decimal("950"), target_pct=20.0)
    assert next_batch_external_ratio(behind) > 0.20

    on_track = evaluate_exploration(Decimal("250"), Decimal("750"), target_pct=20.0)
    assert next_batch_external_ratio(on_track) == 0.20


def test_ratio_is_capped_at_one() -> None:
    starved = evaluate_exploration(Decimal("0"), Decimal("1000"), target_pct=80.0)
    assert next_batch_external_ratio(starved) <= 1.0


def test_gene_converts_to_dna_carrying_external_lineage() -> None:
    gene = DNAGene(
        source="youtube",
        source_ref="vid123",
        hook_type="cost_of_inaction",
        visual_motif="an empty calendar",
        cta_style="SIGN_UP",
        raw_excerpt="explains what waiting costs",
    )
    dna = gene_to_dna(gene, "margin_blind")
    assert dna.is_external
    assert dna.lineage == ["youtube:vid123"]
    assert dna.hook_type == "cost_of_inaction"


def test_concept_family_groups_variants_but_splits_angles() -> None:
    same_family_a = _dna("contrarian_take", "margin", "motif one")
    same_family_b = _dna("contrarian_take", "margin", "motif two")
    other_family = _dna("customer_quote", "margin", "motif one")

    assert same_family_a.concept_family_id == same_family_b.concept_family_id
    assert same_family_a.concept_family_id != other_family.concept_family_id
    assert same_family_a.dna_id != same_family_b.dna_id
