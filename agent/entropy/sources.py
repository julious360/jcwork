"""External DNA harvesters.

Where fresh creative signal comes from when the agent's own history has stopped
producing any. Each harvester returns raw text; ``GeneExtractor`` turns that text
into structured genes.

Honest limits, stated up front:

* **Ad Library** — Meta's official ``ads_archive`` endpoint only supports broad
  keyword search for political and issue ads. For commercial advertisers it serves
  ads for pages you specify. Scraping the public Ad Library web UI would widen this
  but violates Meta's terms, so it is not implemented here: configure
  ``competitor_pages`` with the Page IDs you want to track instead.
* **Podcasts** — show notes and episode descriptions are parsed from RSS. Audio
  transcription (Whisper) is a declared extension, not implemented, because it needs
  a transcription budget and a queue of its own.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Protocol

import httpx

from agent.config import CampaignConfig, Settings, get_settings
from agent.entropy.dna import DNAGene
from agent.llm import LLMClient, LLMError
from agent.logging_setup import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class HarvestedText:
    source: str
    source_ref: str
    text: str


class Harvester(Protocol):
    name: str

    def harvest(self, campaign: CampaignConfig, limit: int = 20) -> list[HarvestedText]: ...


class AdLibraryHarvester:
    """Competitor ads via Meta's official Ad Library API.

    Note this uses the *Ad Library* endpoint, which is separate from the Marketing
    API quota the rate governor protects — reading here does not spend the ad
    account's write budget.
    """

    name = "ad_library"

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        self._settings = settings or get_settings()
        self._http = client or httpx.Client(timeout=60.0)

    def harvest(self, campaign: CampaignConfig, limit: int = 20) -> list[HarvestedText]:
        token = self._settings.meta.access_token.get_secret_value()
        if not token:
            log.info("entropy.ad_library_skipped", reason="no access token configured")
            return []
        if not campaign.competitor_pages:
            log.info("entropy.ad_library_skipped", reason="no competitor_pages configured")
            return []

        results: list[HarvestedText] = []
        for page_id in campaign.competitor_pages:
            try:
                response = self._http.get(
                    f"{self._settings.meta.base_url}/ads_archive",
                    params={
                        "search_page_ids": page_id,
                        "ad_reached_countries": "['US']",
                        "ad_active_status": "ALL",
                        "fields": "ad_creative_bodies,ad_creative_link_titles,page_name",
                        "limit": limit,
                        "access_token": token,
                    },
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("entropy.ad_library_failed", page_id=page_id, error=str(exc))
                continue

            for ad in response.json().get("data", []):
                bodies = ad.get("ad_creative_bodies") or []
                titles = ad.get("ad_creative_link_titles") or []
                text = "\n".join([*bodies, *titles]).strip()
                if text:
                    results.append(
                        HarvestedText(
                            source=self.name,
                            source_ref=f"page:{page_id}",
                            text=text[:4000],
                        )
                    )
        return results[:limit]


class YouTubeHarvester:
    """Transcripts via YouTube's public timedtext endpoint.

    Long-form video is where an audience explains its problems at length and
    unprompted — richer phrasing than any ad corpus.
    """

    name = "youtube"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._http = client or httpx.Client(timeout=45.0, follow_redirects=True)

    def harvest(self, campaign: CampaignConfig, limit: int = 20) -> list[HarvestedText]:
        if not campaign.youtube_channels:
            log.info("entropy.youtube_skipped", reason="no youtube_channels configured")
            return []

        results: list[HarvestedText] = []
        for video_id in campaign.youtube_channels[:limit]:
            transcript = self._fetch_transcript(video_id)
            if transcript:
                results.append(
                    HarvestedText(source=self.name, source_ref=video_id, text=transcript[:8000])
                )
        return results

    def _fetch_transcript(self, video_id: str) -> str:
        try:
            response = self._http.get(
                "https://www.youtube.com/api/timedtext",
                params={"lang": "en", "v": video_id, "fmt": "srv3"},
            )
            if response.status_code != 200 or not response.text.strip():
                return ""
            root = ET.fromstring(response.text)
            segments = [
                "".join(node.itertext()).strip()
                for node in root.iter()
                if node.tag in {"p", "text"}
            ]
            return " ".join(s for s in segments if s)
        except (httpx.HTTPError, ET.ParseError) as exc:
            log.warning("entropy.youtube_failed", video_id=video_id, error=str(exc))
            return ""


class PodcastHarvester:
    """Episode titles and show notes from podcast RSS feeds."""

    name = "podcast"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._http = client or httpx.Client(timeout=45.0, follow_redirects=True)

    def harvest(self, campaign: CampaignConfig, limit: int = 20) -> list[HarvestedText]:
        if not campaign.podcast_feeds:
            log.info("entropy.podcast_skipped", reason="no podcast_feeds configured")
            return []

        results: list[HarvestedText] = []
        for feed_url in campaign.podcast_feeds:
            try:
                response = self._http.get(feed_url)
                response.raise_for_status()
                root = ET.fromstring(response.content)
            except (httpx.HTTPError, ET.ParseError) as exc:
                log.warning("entropy.podcast_failed", feed=feed_url, error=str(exc))
                continue

            for item in root.iter("item"):
                title = _element_text(item, "title")
                description = _strip_html(_element_text(item, "description"))
                text = f"{title}\n{description}".strip()
                if len(text) > 100:
                    results.append(
                        HarvestedText(source=self.name, source_ref=feed_url, text=text[:4000])
                    )
                if len(results) >= limit:
                    break
        return results[:limit]


GENE_SYSTEM = """You extract reusable creative structure from advertising and \
long-form content. You are looking for the shape of an idea, never the specific \
brand or product.

Never copy a competitor's wording or claims. Extract the pattern only."""

GENE_PROMPT = """From the content below, extract up to {n} distinct creative genes.

For each, identify:
- hook_type: one of problem_agitation, before_after, contrarian_take, \
specific_number, customer_quote, cost_of_inaction
- visual_motif: the visual idea in one concrete phrase
- cta_style: the kind of ask being made

Return JSON exactly in this shape:
{{
  "genes": [
    {{"hook_type": "...", "visual_motif": "...", "cta_style": "...",
      "rationale": "what makes this structure work"}}
  ]
}}

CONTENT:
{content}
"""


class GeneExtractor:
    """Turns harvested text into structured genes via the LLM."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def extract(self, harvested: HarvestedText, max_genes: int = 3) -> list[DNAGene]:
        try:
            raw = self._llm.complete_json(
                GENE_PROMPT.format(n=max_genes, content=harvested.text[:6000]),
                system=GENE_SYSTEM,
            )
        except LLMError as exc:
            log.warning("entropy.gene_extraction_failed", source=harvested.source, error=str(exc))
            return []

        genes: list[DNAGene] = []
        for item in raw.get("genes", [])[:max_genes]:
            motif = str(item.get("visual_motif", "")).strip()
            if not motif:
                continue
            genes.append(
                DNAGene(
                    source=harvested.source,
                    source_ref=harvested.source_ref,
                    hook_type=str(item.get("hook_type", "problem_agitation")),
                    visual_motif=motif,
                    cta_style=str(item.get("cta_style", "LEARN_MORE")),
                    raw_excerpt=str(item.get("rationale", ""))[:1000],
                    is_external=True,
                )
            )
        return genes


def build_harvesters(settings: Settings | None = None) -> list[Harvester]:
    return [
        AdLibraryHarvester(settings),
        YouTubeHarvester(),
        PodcastHarvester(),
    ]


def _element_text(item: ET.Element, tag: str) -> str:
    node = item.find(tag)
    return (node.text or "").strip() if node is not None else ""


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()
