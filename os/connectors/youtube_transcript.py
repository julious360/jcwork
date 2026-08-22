#!/usr/bin/env python3
"""YouTube → transcript connector.

Claude has no native way to watch a video, so this bridges the gap: it pulls the
caption track, flattens it to prose, and drops it in `memory/inbox/transcripts/`
where `/transcript-to-newsletter` and the weekly routine pick it up.

Backends, in order of preference:
  1. `yt-dlp` on PATH (best: real titles, auto-generated captions, playlists)
  2. `youtube-transcript-api` if importable (`pip install youtube-transcript-api`)
  3. stdin / a local VTT or SRT file — for anything already captured elsewhere

Usage:
    python os/connectors/youtube_transcript.py https://youtu.be/VIDEOID
    python os/connectors/youtube_transcript.py --file talk.vtt --title "Agency ops"
    pbpaste | python os/connectors/youtube_transcript.py --stdin --title "Sales call"
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "memory" / "inbox" / "transcripts"

TIMESTAMP = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s+-->")
TAGS = re.compile(r"<[^>]+>")


def slugify(text: str, limit: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text[:limit].rstrip("-")) or "untitled"


def video_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else (url if re.fullmatch(r"[A-Za-z0-9_-]{11}", url) else None)


def flatten_captions(raw: str) -> str:
    """VTT/SRT → prose. Caption files repeat lines as they scroll; dedupe those."""
    lines: list[str] = []
    for line in raw.splitlines():
        line = TAGS.sub("", line).strip()
        if not line or line in ("WEBVTT",) or TIMESTAMP.match(line) or line.isdigit():
            continue
        if line.startswith(("Kind:", "Language:", "NOTE ", "STYLE")):
            continue
        if lines and line == lines[-1]:
            continue
        lines.append(line)

    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()
    # Paragraph every ~5 sentences so the file is readable and diffable.
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return "\n\n".join(
        " ".join(sentences[i : i + 5]) for i in range(0, len(sentences), 5)
    ).strip()


def fetch_with_ytdlp(url: str, lang: str) -> tuple[str, dict[str, str]] | None:
    if not shutil.which("yt-dlp"):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            "yt-dlp", "--skip-download",
            "--write-subs", "--write-auto-subs",
            "--sub-langs", f"{lang},{lang}-*",
            "--sub-format", "vtt/srt/best",
            "--write-info-json",
            "--paths", tmp, "-o", "%(id)s", url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
        if proc.returncode != 0:
            print(f"yt-dlp failed:\n{proc.stderr.strip()[-800:]}", file=sys.stderr)
            return None

        subs = sorted(Path(tmp).glob("*.vtt")) + sorted(Path(tmp).glob("*.srt"))
        if not subs:
            print("yt-dlp found no caption track for this video.", file=sys.stderr)
            return None

        meta: dict[str, str] = {}
        info_files = list(Path(tmp).glob("*.info.json"))
        if info_files:
            info = json.loads(info_files[0].read_text(encoding="utf-8"))
            meta = {
                "title": str(info.get("title", "")),
                "channel": str(info.get("uploader", "")),
                "duration": str(info.get("duration_string", info.get("duration", ""))),
                "upload_date": str(info.get("upload_date", "")),
            }
        return subs[0].read_text(encoding="utf-8"), meta


def fetch_with_api(url: str, lang: str) -> tuple[str, dict[str, str]] | None:
    vid = video_id(url)
    if not vid:
        return None
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        chunks = YouTubeTranscriptApi.get_transcript(vid, languages=[lang, "en"])
    except Exception as exc:  # noqa: BLE001 - library raises many private types
        print(f"youtube-transcript-api failed: {exc}", file=sys.stderr)
        return None
    return " ".join(c["text"] for c in chunks), {"title": vid}


def write_transcript(body: str, meta: dict[str, str], source: str) -> Path:
    title = meta.get("title") or "untitled"
    stem = f"{date.today().isoformat()}-{slugify(title)}"
    INBOX.mkdir(parents=True, exist_ok=True)
    out = INBOX / f"{stem}.md"

    words = len(body.split())
    front = [
        "---",
        f'title: "{title.replace(chr(34), chr(39))}"',
        f"source: {source}",
        f"channel: {meta.get('channel', '')}",
        f"duration: {meta.get('duration', '')}",
        f"captured: {date.today().isoformat()}",
        f"words: {words}",
        "status: unprocessed",
        "---",
        "",
        f"# {title}",
        "",
    ]
    out.write_text("\n".join(front) + body + "\n", encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture a transcript into memory/inbox")
    ap.add_argument("url", nargs="?", help="YouTube URL or 11-character video id")
    ap.add_argument("--file", type=Path, help="local .vtt/.srt/.txt instead of fetching")
    ap.add_argument("--stdin", action="store_true", help="read caption text from stdin")
    ap.add_argument("--title", default="", help="title to use (required for --file/--stdin)")
    ap.add_argument("--lang", default="en")
    args = ap.parse_args()

    if args.stdin or args.file:
        raw = sys.stdin.read() if args.stdin else args.file.read_text(encoding="utf-8")
        meta = {"title": args.title or (args.file.stem if args.file else "pasted transcript")}
        source = str(args.file) if args.file else "stdin"
    elif args.url:
        result = fetch_with_ytdlp(args.url, args.lang) or fetch_with_api(args.url, args.lang)
        if result is None:
            print(
                "No transcript backend succeeded. Install one:\n"
                "  pipx install yt-dlp                  # preferred\n"
                "  pip install youtube-transcript-api   # fallback\n"
                "or capture the captions elsewhere and pipe them in with --stdin.",
                file=sys.stderr,
            )
            return 2
        raw, meta = result
        source = args.url
    else:
        ap.error("give a URL, or --file / --stdin")
        return 2

    body = flatten_captions(raw)
    if len(body.split()) < 50:
        print(f"Only {len(body.split())} words extracted — refusing to write a stub.", file=sys.stderr)
        return 3

    out = write_transcript(body, meta, source)
    print(f"wrote {out.relative_to(ROOT)} ({len(body.split())} words)")
    print(f'next: claude -p "/transcript-to-newsletter {out.relative_to(ROOT)}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
