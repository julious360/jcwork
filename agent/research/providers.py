"""Research providers: where raw statements of customer pain come from.

All three satisfy the same protocol, so the ranker never learns which one ran. The
mock is fixture-backed and is what runs until Perplexity/Reddit credentials exist —
it keeps the whole pipeline exercisable end to end without network access.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import httpx

from agent.config import CampaignConfig, Settings, get_settings
from agent.logging_setup import get_logger
from agent.research.models import SourceDocument

log = get_logger(__name__)

FIXTURES = Path(__file__).parent / "fixtures"


class ResearchProvider(Protocol):
    name: str

    def fetch(self, campaign: CampaignConfig, limit: int = 50) -> list[SourceDocument]: ...


class MockResearchProvider:
    """Fixture-backed provider.

    Documents are templated with the configured category so the offline path still
    produces category-appropriate output rather than a hardcoded vertical.
    """

    name = "mock"

    def __init__(self, fixture_path: Path | None = None) -> None:
        self._fixture_path = fixture_path or FIXTURES / "sample_pain_points.json"

    def fetch(self, campaign: CampaignConfig, limit: int = 50) -> list[SourceDocument]:
        raw = json.loads(self._fixture_path.read_text())
        documents = [
            SourceDocument(
                provider=self.name,
                url=item.get("url", ""),
                title=item.get("title", "").format(category=campaign.product_category),
                body=item["body"].format(category=campaign.product_category),
                score=int(item.get("score", 0)),
            )
            for item in raw["documents"]
        ]
        return documents[:limit]


class RedditProvider:
    """Reddit via the public OAuth API.

    Reddit is deliberately included: people describe problems there in their own
    words, before a marketer has reframed them. That phrasing is the raw material
    for hooks.
    """

    name = "reddit"

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        self._settings = (settings or get_settings()).research
        self._http = client or httpx.Client(timeout=30.0)
        self._token: str | None = None

    def _authenticate(self) -> str:
        if self._token:
            return self._token
        client_id = self._settings.reddit_client_id.get_secret_value()
        client_secret = self._settings.reddit_client_secret.get_secret_value()
        if not client_id or not client_secret:
            raise RuntimeError("Reddit credentials are not configured")

        response = self._http.post(
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            headers={"User-Agent": self._settings.reddit_user_agent},
        )
        response.raise_for_status()
        self._token = str(response.json()["access_token"])
        return self._token

    def fetch(self, campaign: CampaignConfig, limit: int = 50) -> list[SourceDocument]:
        token = self._authenticate()
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": self._settings.reddit_user_agent,
        }
        documents: list[SourceDocument] = []
        per_sub = max(1, limit // max(1, len(campaign.research_subreddits)))

        for subreddit in campaign.research_subreddits:
            try:
                response = self._http.get(
                    f"https://oauth.reddit.com/r/{subreddit}/search",
                    params={
                        "q": campaign.product_category,
                        "restrict_sr": "true",
                        "sort": "relevance",
                        "t": "year",
                        "limit": per_sub,
                    },
                    headers=headers,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                # One bad subreddit must not sink the whole research run.
                log.warning("research.reddit_failed", subreddit=subreddit, error=str(exc))
                continue

            for child in response.json().get("data", {}).get("children", []):
                data = child.get("data", {})
                body = (data.get("selftext") or "").strip()
                if len(body) < 80:  # titles alone carry too little signal
                    continue
                documents.append(
                    SourceDocument(
                        provider=self.name,
                        url=f"https://reddit.com{data.get('permalink', '')}",
                        title=data.get("title", ""),
                        body=body[:4000],
                        score=int(data.get("score", 0)),
                    )
                )
        return documents[:limit]


class PerplexityProvider:
    """Perplexity — synthesised, citation-backed answers rather than raw posts."""

    name = "perplexity"

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        self._settings = (settings or get_settings()).research
        self._http = client or httpx.Client(timeout=90.0)

    def fetch(self, campaign: CampaignConfig, limit: int = 50) -> list[SourceDocument]:
        key = self._settings.perplexity_api_key.get_secret_value()
        if not key:
            raise RuntimeError("Perplexity API key is not configured")

        queries = campaign.research_queries or [
            f"What are the biggest frustrations people have with {campaign.product_category}?"
        ]
        documents: list[SourceDocument] = []
        for query in queries:
            try:
                response = self._http.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": "sonar-pro",
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Report what real users say, in their own words. "
                                    "Quote verbatim complaints. Do not summarise into "
                                    "marketing language."
                                ),
                            },
                            {"role": "user", "content": query},
                        ],
                    },
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("research.perplexity_failed", query=query, error=str(exc))
                continue

            payload: dict[str, Any] = response.json()
            content = payload["choices"][0]["message"]["content"]
            citations = payload.get("citations", [])
            documents.append(
                SourceDocument(
                    provider=self.name,
                    url=citations[0] if citations else "",
                    title=query,
                    body=content,
                )
            )
        return documents[:limit]


def build_provider(settings: Settings | None = None) -> ResearchProvider:
    """Best available provider; mock when nothing is configured."""
    resolved = (settings or get_settings()).research
    if resolved.perplexity_api_key.get_secret_value():
        return PerplexityProvider(settings)
    if resolved.reddit_client_id.get_secret_value():
        return RedditProvider(settings)
    log.info("research.using_mock_provider", detail="no research credentials configured")
    return MockResearchProvider()
