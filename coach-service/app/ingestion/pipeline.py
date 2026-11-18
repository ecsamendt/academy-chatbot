"""Ingestion: lesson video -> transcript -> passages -> embeddings -> index.

Every step is idempotent: re-ingesting a lesson replaces its passages in one transaction.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import numpy as np
import yaml

from app.config import get_settings
from app.db import get_pool
from app.ingestion import audio, vimeo
from app.ingestion.chunking import Passage, chunk_segments
from app.ingestion.wordpress import Lesson, WordPressClient
from app.llm import get_provider
from app.llm.base import Transcript, TranscriptSegment

log = logging.getLogger("coach.ingest")

TOOLS_FILE = Path(__file__).resolve().parents[2] / "tools" / "tools.yaml"


def _set_lesson_status(lesson: Lesson, status: str, detail: str | None = None, count: int = 0) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO lessons (lesson_id, title, url, course_title, vimeo_ids, wp_modified, status,
                                 detail, passage_count, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (lesson_id) DO UPDATE SET
                title = EXCLUDED.title, url = EXCLUDED.url, course_title = EXCLUDED.course_title,
                vimeo_ids = EXCLUDED.vimeo_ids, wp_modified = EXCLUDED.wp_modified,
                status = EXCLUDED.status, detail = EXCLUDED.detail,
                passage_count = EXCLUDED.passage_count, updated_at = now()
            """,
            (str(lesson.id), lesson.title, lesson.url, lesson.course_title, lesson.vimeo_ids,
             lesson.modified, status, detail, count),
        )


def _already_indexed(lesson: Lesson) -> bool:
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT wp_modified, status FROM lessons WHERE lesson_id = %s", (str(lesson.id),)
        ).fetchone()
    return bool(row and row["status"] == "indexed" and row["wp_modified"] == lesson.modified)


def transcribe_video(video_id: str) -> Transcript:
    """Download audio for one Vimeo video and transcribe it with segment timestamps."""
    settings = get_settings()
    work = settings.work_dir / "audio" / video_id
    work.mkdir(parents=True, exist_ok=True)
    cache = settings.work_dir / "transcripts" / f"{video_id}.json"
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        return Transcript(language=data["language"], segments=[TranscriptSegment(**s) for s in data["segments"]])
    try:
        video = vimeo.get_video(video_id)
        mp3 = audio.extract_audio(video.download_url, work / "audio.mp3")
        provider = get_provider()
        segments: list[TranscriptSegment] = []
        language = "es"
        for part in audio.split_for_upload(mp3):
            t = provider.transcribe(str(part.path), language="es")
            language = t.language
            segments.extend(
                TranscriptSegment(s.start + part.offset_sec, s.end + part.offset_sec, s.text) for s in t.segments
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    transcript = Transcript(language=language, segments=segments)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps({"language": language, "segments": [s.__dict__ for s in segments]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return transcript


def _replace_passages(source_type: str, source_id: str, rows: list[dict]) -> None:
    with get_pool().connection() as conn:
        with conn.transaction():
            conn.execute("DELETE FROM passages WHERE source_type = %s AND source_id = %s", (source_type, source_id))
            for r in rows:
                conn.execute(
                    """
                    INSERT INTO passages (source_type, source_id, course_id, course_title, module_title,
                        lesson_title, lesson_url, vimeo_id, start_sec, end_sec, text, topics, language,
                        is_public, allowed_memberships, required_plan_label, embedding)
                    VALUES (%(source_type)s, %(source_id)s, %(course_id)s, %(course_title)s,
                        %(module_title)s, %(lesson_title)s, %(lesson_url)s, %(vimeo_id)s, %(start_sec)s,
                        %(end_sec)s, %(text)s, %(topics)s, %(language)s, %(is_public)s,
                        %(allowed_memberships)s, %(required_plan_label)s, %(embedding)s)
                    """,
                    r,
                )


def lesson_rows(lesson: Lesson, video_id: str, language: str, passages: list[Passage],
                embeddings: list[list[float]]) -> list[dict]:
    return [
        {
            "source_type": "lesson",
            "source_id": str(lesson.id),
            "course_id": str(lesson.course_id) if lesson.course_id else None,
            "course_title": lesson.course_title,
            "module_title": lesson.section_title,
            "lesson_title": lesson.title,
            "lesson_url": lesson.url,
            "vimeo_id": video_id,
            "start_sec": p.start_sec,
            "end_sec": p.end_sec,
            "text": p.text,
            "topics": [],
            "language": language,
            "is_public": lesson.is_public,
            "allowed_memberships": lesson.membership_ids,
            "required_plan_label": lesson.plan_label,
            "embedding": np.array(e, dtype=np.float32),
        }
        for p, e in zip(passages, embeddings, strict=True)
    ]


def embedding_text(lesson: Lesson, p: Passage) -> str:
    # Course and lesson names help retrieval match questions phrased around the topic.
    header = " > ".join(x for x in (lesson.course_title, lesson.section_title, lesson.title) if x)
    return f"{header}\n{p.text}"


def ingest_lesson(lesson_id: int, force: bool = False, wp: WordPressClient | None = None) -> str:
    wp = wp or WordPressClient()
    lesson = wp.get_lesson(lesson_id)
    if lesson is None or lesson.status != "publish":
        delete_lesson(lesson_id)
        return "removed"
    return ingest_one(lesson, force=force)


def refresh_access(lesson: Lesson) -> None:
    """Access rules can change without the lesson changing; always re-apply them."""
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE passages SET is_public = %s, allowed_memberships = %s, required_plan_label = %s "
            "WHERE source_type = 'lesson' AND source_id = %s",
            (lesson.is_public, lesson.membership_ids, lesson.plan_label, str(lesson.id)),
        )


def ingest_one(lesson: Lesson, force: bool = False) -> str:
    if not force and _already_indexed(lesson):
        refresh_access(lesson)
        return "unchanged"
    ids = lesson.vimeo_ids
    if not ids:
        _replace_passages("lesson", str(lesson.id), [])
        _set_lesson_status(lesson, "no_video", "No Vimeo embed found in lesson content")
        return "no_video"
    if len(ids) > 1:
        # Flag instead of guessing which video is the lesson.
        _replace_passages("lesson", str(lesson.id), [])
        _set_lesson_status(lesson, "multiple_videos", f"Found Vimeo IDs {ids}; set vimeo_ids in WordPress")
        return "multiple_videos"
    try:
        transcript = transcribe_video(ids[0])
        passages = chunk_segments(transcript.segments)
        embeddings = get_provider().embed([embedding_text(lesson, p) for p in passages]) if passages else []
        _replace_passages("lesson", str(lesson.id),
                          lesson_rows(lesson, ids[0], transcript.language, passages, embeddings))
        _set_lesson_status(lesson, "indexed", None, len(passages))
        return "indexed"
    except Exception as exc:
        log.exception("lesson %s failed", lesson.id)
        _set_lesson_status(lesson, "error", str(exc)[:1000])
        raise


def ingest_all(force: bool = False) -> dict[str, int]:
    wp = WordPressClient()
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for lesson in wp.iter_lessons():
        seen.add(str(lesson.id))
        try:
            status = ingest_one(lesson, force=force)
        except Exception:
            status = "error"
        counts[status] = counts.get(status, 0) + 1
        log.info("lesson %s %s: %s", lesson.id, lesson.title, status)
    # Lessons no longer published in WordPress leave the index.
    with get_pool().connection() as conn:
        stale = [r["lesson_id"] for r in conn.execute("SELECT lesson_id FROM lessons").fetchall()
                 if r["lesson_id"] not in seen]
    for lid in stale:
        delete_lesson(int(lid))
    counts["removed"] = len(stale)
    return counts


def delete_lesson(lesson_id: int) -> None:
    with get_pool().connection() as conn:
        conn.execute("DELETE FROM passages WHERE source_type = 'lesson' AND source_id = %s", (str(lesson_id),))
        conn.execute("DELETE FROM lessons WHERE lesson_id = %s", (str(lesson_id),))


def load_tools(path: Path = TOOLS_FILE) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def tool_text(t: dict) -> str:
    examples = "\n".join(f"- {e}" for e in t.get("examples") or [])
    return f"{t['name']}\n{t['description'].strip()}\nPreguntas que responde:\n{examples}"


def ingest_tools(path: Path = TOOLS_FILE) -> int:
    tools = load_tools(path)
    embeddings = get_provider().embed([tool_text(t) for t in tools]) if tools else []
    with get_pool().connection() as conn:
        conn.execute("DELETE FROM passages WHERE source_type = 'tool'")
    for t, e in zip(tools, embeddings, strict=True):
        _replace_passages("tool", t["key"], [{
            "source_type": "tool", "source_id": t["key"], "course_id": None, "course_title": None,
            "module_title": None, "lesson_title": t["name"], "lesson_url": t["url"], "vimeo_id": None,
            "start_sec": None, "end_sec": None, "text": tool_text(t), "topics": [], "language": "es",
            "is_public": bool(t.get("is_public")),
            "allowed_memberships": [int(m) for m in t.get("membership_ids") or []],
            "required_plan_label": t.get("plan_label"), "embedding": np.array(e, dtype=np.float32),
        }])
    return len(tools)
