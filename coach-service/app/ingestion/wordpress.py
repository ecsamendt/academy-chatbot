"""Reads MemberPress Courses lessons from the Socio Coach WordPress plugin's REST endpoint.

The plugin (wp-plugin/socio-coach) exposes:
  GET /wp-json/socio-coach/v1/lessons?page=N   -> {"lessons": [...], "total_pages": N}
  GET /wp-json/socio-coach/v1/lessons/<id>     -> lesson, or 404 when unpublished/deleted
both authenticated with the X-Socio-Ingest-Secret header.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx

from app.config import get_settings

VIMEO_ID_PATTERNS = [
    re.compile(r"player\.vimeo\.com/video/(\d{5,12})"),
    re.compile(r"vimeo\.com/(?:video/|channels/[\w-]+/|groups/[\w-]+/videos/|manage/videos/)?(\d{5,12})(?![\d])"),
]


@dataclass
class Lesson:
    id: int
    title: str
    url: str
    status: str
    modified: str
    course_id: int | None
    course_title: str | None
    section_title: str | None
    content: str
    is_public: bool
    membership_ids: list[int] = field(default_factory=list)
    plan_label: str | None = None
    vimeo_ids_override: list[str] = field(default_factory=list)

    @property
    def vimeo_ids(self) -> list[str]:
        return self.vimeo_ids_override or extract_vimeo_ids(self.content)


def extract_vimeo_ids(html: str) -> list[str]:
    """Vimeo IDs embedded in a lesson's content, in order, without duplicates."""
    found: list[tuple[int, str]] = []
    for pat in VIMEO_ID_PATTERNS:
        found.extend((m.start(), m.group(1)) for m in pat.finditer(html or ""))
    ids: list[str] = []
    for _, vid in sorted(found):
        if vid not in ids:
            ids.append(vid)
    return ids


def _lesson(d: dict) -> Lesson:
    return Lesson(
        id=int(d["id"]),
        title=d["title"],
        url=d["url"],
        status=d.get("status", "publish"),
        modified=d.get("modified", ""),
        course_id=d.get("course_id"),
        course_title=d.get("course_title"),
        section_title=d.get("section_title"),
        content=d.get("content", ""),
        is_public=bool(d.get("is_public")),
        membership_ids=[int(m) for m in d.get("membership_ids") or []],
        plan_label=d.get("plan_label"),
        vimeo_ids_override=[str(v) for v in d.get("vimeo_ids") or []],
    )


class WordPressClient:
    def __init__(self) -> None:
        s = get_settings()
        self.http = httpx.Client(
            base_url=s.wp_base_url.rstrip("/") + "/wp-json/socio-coach/v1",
            headers={"X-Socio-Ingest-Secret": s.wp_ingest_secret},
            timeout=60,
        )

    def iter_lessons(self) -> Iterator[Lesson]:
        page = 1
        while True:
            r = self.http.get("/lessons", params={"page": page, "per_page": 50})
            r.raise_for_status()
            data = r.json()
            for d in data["lessons"]:
                yield _lesson(d)
            if page >= int(data.get("total_pages", 1)):
                return
            page += 1

    def get_lesson(self, lesson_id: int) -> Lesson | None:
        r = self.http.get(f"/lessons/{lesson_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return _lesson(r.json())
