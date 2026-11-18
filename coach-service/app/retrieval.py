"""Search passages and split results into ones the member may see and ones that are locked."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.auth import Member
from app.db import get_pool


@dataclass
class Hit:
    id: int
    source_type: str
    source_id: str
    course_title: str | None
    module_title: str | None
    lesson_title: str
    lesson_url: str
    start_sec: int | None
    end_sec: int | None
    text: str
    is_public: bool
    allowed_memberships: list[int]
    required_plan_label: str | None
    score: float


@dataclass
class SearchResult:
    accessible: list[Hit] = field(default_factory=list)
    locked: list[Hit] = field(default_factory=list)

    @property
    def top_accessible(self) -> float:
        return max((h.score for h in self.accessible), default=0.0)

    @property
    def top_locked(self) -> float:
        return max((h.score for h in self.locked), default=0.0)


def can_access(member: Member, is_public: bool, allowed_memberships: list[int]) -> bool:
    """Gate for every passage. Empty list and not public = staff only (fail closed)."""
    if member.staff or is_public:
        return True
    return bool(set(member.memberships) & set(allowed_memberships or []))


def split_by_access(member: Member, hits: list[Hit]) -> SearchResult:
    result = SearchResult()
    for h in hits:
        (result.accessible if can_access(member, h.is_public, h.allowed_memberships) else result.locked).append(h)
    return result


def search(member: Member, query_embedding: list[float], k: int) -> SearchResult:
    """Fetch the nearest passages across all content, then split by access.

    Locked hits are kept only so the service can say *which course* covers the
    question; their text is never sent to the model or returned to the member.
    """
    sql = """
        SELECT id, source_type, source_id, course_title, module_title, lesson_title,
               lesson_url, start_sec, end_sec, text, is_public, allowed_memberships,
               required_plan_label, 1 - (embedding <=> %(q)s) AS score
        FROM passages
        ORDER BY embedding <=> %(q)s
        LIMIT %(limit)s
    """
    with get_pool().connection() as conn:
        rows = conn.execute(sql, {"q": np.array(query_embedding, dtype=np.float32), "limit": k * 3}).fetchall()
    hits = [Hit(**{**r, "score": float(r["score"])}) for r in rows]
    result = split_by_access(member, hits)
    result.accessible = result.accessible[:k]
    result.locked = result.locked[:k]
    return result
