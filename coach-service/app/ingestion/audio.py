"""ffmpeg helpers: pull a small mono audio track from a video, split it under the
transcription upload limit (25 MB), and report each part's start offset."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_UPLOAD_BYTES = 24 * 1024 * 1024
PART_SECONDS = 20 * 60  # 20 min at 32 kbps is about 4.8 MB


@dataclass
class AudioPart:
    path: Path
    offset_sec: float


def _run(args: list[str]) -> str:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{args[0]} failed: {proc.stderr[-1500:]}")
    return proc.stdout


def extract_audio(source: str, out_path: Path) -> Path:
    """source can be a local file or an https URL (ffmpeg streams it)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", source, "-vn", "-ac", "1", "-ar", "16000",
          "-b:a", "32k", str(out_path)])
    return out_path


def duration_sec(path: Path) -> float:
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return float(out.strip())


def split_for_upload(path: Path) -> list[AudioPart]:
    if path.stat().st_size <= MAX_UPLOAD_BYTES:
        return [AudioPart(path, 0.0)]
    pattern = path.with_name(path.stem + "_part%03d" + path.suffix)
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-f", "segment", "-segment_time",
          str(PART_SECONDS), "-c", "copy", str(pattern)])
    parts = sorted(path.parent.glob(path.stem + "_part*" + path.suffix))
    result, offset = [], 0.0
    for p in parts:
        result.append(AudioPart(p, offset))
        offset += duration_sec(p)  # real durations, since copy-mode cuts land on frame boundaries
    return result
