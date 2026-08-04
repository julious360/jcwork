"""The write-only constraint, enforced by the build.

Meta's Marketing API is points-metered per ad account and the default access tier is
documented as unsuitable for production. Polling insights through it is how apps get
throttled and accounts get restricted. Performance data comes from ClickHouse.

These tests exist so that constraint cannot quietly erode: adding a read endpoint to
the client breaks CI rather than shipping.
"""

from __future__ import annotations

import ast
import inspect

from agent.meta import write_client
from agent.meta.write_client import WRITE_METHODS, MetaWriteClient

# Anything matching these on the public surface would mean the agent had started
# pulling data through the Marketing API.
FORBIDDEN_FRAGMENTS = (
    "insight",
    "report",
    "fetch",
    "list_",
    "get_ads",
    "get_campaigns",
    "get_adsets",
    "read_",
    "query",
    "stats",
    "metrics",
)

ALLOWED_PUBLIC = WRITE_METHODS | {"execute", "close", "verify_object_status"}


def _public_methods() -> set[str]:
    return {
        name
        for name, _ in inspect.getmembers(MetaWriteClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def test_public_surface_is_exactly_the_allowed_set() -> None:
    assert _public_methods() == ALLOWED_PUBLIC


def test_no_method_name_suggests_reading() -> None:
    for name in _public_methods():
        if name == "verify_object_status":
            continue  # the one bounded exception, tested separately below
        lowered = name.lower()
        for fragment in FORBIDDEN_FRAGMENTS:
            assert fragment not in lowered, (
                f"{name!r} looks like a read endpoint. Performance data must come "
                f"from ClickHouse, not the Marketing API."
            )


def test_all_declared_write_methods_exist() -> None:
    for name in WRITE_METHODS:
        assert callable(getattr(MetaWriteClient, name, None)), f"missing mutation {name!r}"


def _code_strings(source: str) -> list[str]:
    """Every string literal in the source *except* docstrings.

    Scanning raw text would flag the module's own documentation, which discusses
    ``/insights`` precisely to explain why it is never called. What matters is
    whether such a path appears in executable code.
    """
    tree = ast.parse(source)
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node not in docstrings
    ]


def test_no_code_path_references_an_insights_endpoint() -> None:
    """Guards against a raw ``/insights`` request slipping in below the method layer."""
    for literal in _code_strings(inspect.getsource(write_client)):
        assert "/insights" not in literal
        assert "ads_insights" not in literal


def test_verification_requests_status_fields_only() -> None:
    """The single read path may fetch status fields and nothing else."""
    source = inspect.getsource(MetaWriteClient.verify_object_status)
    literals = _code_strings("class _S:\n" + source)

    assert "id,status,effective_status" in literals
    # No field list may request the expensive reporting columns.
    for literal in literals:
        for costly in ("spend", "impressions", "clicks", "actions", "insights"):
            assert costly not in literal


def test_verification_can_be_disabled(monkeypatch) -> None:
    from agent.config import Settings

    settings = Settings()
    settings.meta.allow_status_verification = False
    client = MetaWriteClient(settings=settings)
    assert client.verify_object_status("123") is None
