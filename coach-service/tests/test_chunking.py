from app.ingestion.chunking import chunk_segments
from app.llm.base import TranscriptSegment as S


def segs(n, length=8.0, sentence_every=2):
    out = []
    for i in range(n):
        end = "." if (i + 1) % sentence_every == 0 else ","
        out.append(S(i * length, (i + 1) * length, f"frase {i}{end}"))
    return out


def test_passages_respect_length_bounds():
    passages = chunk_segments(segs(60))
    assert len(passages) > 3
    for p in passages[:-1]:
        assert 30 <= p.end_sec - p.start_sec <= 90 + 8


def test_cuts_land_on_sentence_ends():
    for p in chunk_segments(segs(60))[:-1]:
        assert p.text.endswith(".")


def test_consecutive_passages_overlap_by_one_segment():
    a, b = chunk_segments(segs(60))[:2]
    assert b.start_sec < a.end_sec
    assert a.text.split()[-2:] == b.text.split()[:2]


def test_forced_cut_without_punctuation():
    passages = chunk_segments([S(i * 10.0, (i + 1) * 10.0, f"sin punto {i}") for i in range(30)])
    assert all(p.end_sec - p.start_sec <= 100 for p in passages)


def test_short_tail_folded_into_previous():
    data = segs(10, length=8.0)  # 80 s total
    data.append(S(80.0, 84.0, "fin."))
    passages = chunk_segments(data)
    assert passages[-1].end_sec == 84
    assert passages[-1].text.endswith("fin.")
    assert all(p.end_sec - p.start_sec >= 15 for p in passages)


def test_all_text_kept():
    data = segs(37)
    joined = " ".join(p.text for p in chunk_segments(data))
    for s in data:
        assert s.text in joined


def test_empty_input():
    assert chunk_segments([]) == []
