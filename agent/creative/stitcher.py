"""Frame stitching for longer video ads.

AI-avatar vendors cap individual clips well below the length a 60-90s ad needs, so
longer spots are assembled from segments here rather than requested wholesale.
Crossfades between segments matter: hard cuts between separately-generated avatar
clips read as glitches, which is exactly the tell that makes UGC-style video stop
working.

Shells out to ffmpeg. Availability is probed rather than assumed, so a host without
ffmpeg produces a clear error instead of a confusing subprocess failure.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agent.logging_setup import get_logger

log = get_logger(__name__)


class FFmpegUnavailableError(RuntimeError):
    pass


@dataclass(slots=True)
class StitchOptions:
    crossfade_seconds: float = 0.4
    audio_bed: Path | None = None
    audio_bed_volume: float = 0.12
    output_fps: int = 30


class VideoStitcher:
    def __init__(self, ffmpeg_binary: str = "ffmpeg") -> None:
        self._ffmpeg = ffmpeg_binary

    @property
    def available(self) -> bool:
        return shutil.which(self._ffmpeg) is not None

    def _require(self) -> None:
        if not self.available:
            raise FFmpegUnavailableError(
                f"{self._ffmpeg!r} not found on PATH. Install ffmpeg "
                "(the Dockerfile does this) or set ADAGENT_CREATIVE__FFMPEG_BINARY."
            )

    def stitch(
        self, segments: list[Path], output_path: Path, options: StitchOptions | None = None
    ) -> Path:
        """Concatenate segments with crossfades, optionally over an audio bed."""
        self._require()
        if not segments:
            raise ValueError("no segments to stitch")

        opts = options or StitchOptions()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if len(segments) == 1 and opts.audio_bed is None:
            shutil.copy(segments[0], output_path)
            return output_path

        command = [self._ffmpeg, "-y"]
        for segment in segments:
            command += ["-i", str(segment)]
        if opts.audio_bed is not None:
            command += ["-i", str(opts.audio_bed)]

        filter_graph, video_label, audio_label = self._build_filter(len(segments), opts)
        command += ["-filter_complex", filter_graph, "-map", video_label]
        if audio_label:
            command += ["-map", audio_label]
        command += [
            "-r",
            str(opts.output_fps),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",  # web playback starts before full download
            str(output_path),
        ]

        log.info("creative.stitching", segments=len(segments), output=str(output_path))
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr[-2000:]}")
        return output_path

    def _build_filter(self, count: int, opts: StitchOptions) -> tuple[str, str, str]:
        """Chained xfade/acrossfade graph.

        Offsets are approximated from a nominal segment duration; vendor clips in a
        given batch are near-uniform in length, and ffmpeg clamps an overshoot.
        """
        parts: list[str] = []
        nominal = 5.0

        if count == 1:
            return "[0:v]null[vout];[0:a]anull[aout]", "[vout]", "[aout]"

        video_prev, audio_prev = "[0:v]", "[0:a]"
        for i in range(1, count):
            v_out = f"[v{i}]"
            a_out = f"[a{i}]"
            offset = max(0.1, nominal * i - opts.crossfade_seconds * i)
            parts.append(
                f"{video_prev}[{i}:v]xfade=transition=fade:"
                f"duration={opts.crossfade_seconds}:offset={offset:.2f}{v_out}"
            )
            parts.append(f"{audio_prev}[{i}:a]acrossfade=d={opts.crossfade_seconds}{a_out}")
            video_prev, audio_prev = v_out, a_out

        if opts.audio_bed is not None:
            bed_index = count
            parts.append(
                f"[{bed_index}:a]volume={opts.audio_bed_volume}[bed];"
                f"{audio_prev}[bed]amix=inputs=2:duration=first[amixed]"
            )
            audio_prev = "[amixed]"

        return ";".join(parts), video_prev, audio_prev

    def probe_duration(self, path: Path) -> float | None:
        """Segment duration in seconds via ffprobe, or None if unavailable."""
        ffprobe = self._ffmpeg.replace("ffmpeg", "ffprobe")
        if shutil.which(ffprobe) is None:
            return None
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            return None
