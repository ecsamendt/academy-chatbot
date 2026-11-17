"""Turn timestamped transcript segments into ~30-90 s passages, cut at sentence ends,
with one segment of overlap between consecutive passages."""

from __future__ import annotations

from dataclasses import dataclass

from app.llm.base import TranscriptSegment

SENTENCE_END = (".", "?", "!", "…", "?»", ".»", '."', '?"')


@dataclass
class Passage:
    start_sec: int
    end_sec: int
    text: str


def _ends_sentence(text: str) -> bool:
    return text.rstrip().endswith(SENTENCE_END)


def _make(segs: list[TranscriptSegment]) -> Passage:
    return Passage(
        start_sec=int(segs[0].start),
        end_sec=int(round(segs[-1].end)),
        text=" ".join(s.text.strip() for s in segs if s.text.strip()),
    )


def chunk_segments(
    segments: list[TranscriptSegment],
    min_sec: float = 30.0,
    max_sec: float = 90.0,
    overlap_segments: int = 1,
) -> list[Passage]:
    segs = [s for s in segments if s.text.strip()]
    passages: list[Passage] = []
    current: list[TranscriptSegment] = []
    new_since_cut = 0  # segments added since the last cut (excludes overlap carry-over)

    for seg in segs:
        current.append(seg)
        new_since_cut += 1
        length = current[-1].end - current[0].start
        if (length >= min_sec and _ends_sentence(seg.text)) or length >= max_sec:
            passages.append(_make(current))
            current = current[-overlap_segments:] if overlap_segments else []
            new_since_cut = 0

    if new_since_cut:
        tail = _make(current)
        # Fold a very short tail into the previous passage instead of leaving a fragment.
        if passages and tail.end_sec - tail.start_sec < min_sec / 2:
            prev = passages[-1]
            extra = current[-new_since_cut:]
            passages[-1] = Passage(prev.start_sec, tail.end_sec,
                                   (prev.text + " " + " ".join(s.text.strip() for s in extra)).strip())
        else:
            passages.append(tail)
    return passages
